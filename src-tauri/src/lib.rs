use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{LogicalSize, Manager, PhysicalPosition, PhysicalSize};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use uuid::Uuid;

const MAX_LAUNCHES: u8 = 3;
const READINESS_TIMEOUT: Duration = Duration::from_secs(5);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(5);
const STARTUP_RETRY_BACKOFF: Duration = Duration::from_millis(100);

const NORMAL_MIN_SIZE: WindowSize = WindowSize {
    width: 980,
    height: 620,
};
const COMPACT_MIN_SIZE: WindowSize = WindowSize {
    width: 320,
    height: 180,
};
const CHAMP_SELECT_SIZE: WindowSize = WindowSize {
    width: 560,
    height: 380,
};
const IN_GAME_SIZE: WindowSize = WindowSize {
    width: 440,
    height: 240,
};
const IN_GAME_EXPANDED_SIZE: WindowSize = WindowSize {
    width: 720,
    height: 520,
};
const COMPANION_MARGIN: u32 = 24;

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Serialize)]
#[serde(tag = "mode", rename_all = "kebab-case")]
enum CompanionMode {
    Idle,
    ChampSelect,
    InGame { expanded: bool },
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct WindowSize {
    width: u32,
    height: u32,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct NormalGeometry {
    position: (i32, i32),
    size: WindowSize,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct CompanionWindowState {
    mode: CompanionMode,
    always_on_top: bool,
    translucent: bool,
    min_size: WindowSize,
    normal_geometry_saved: bool,
    normal_geometry: Option<NormalGeometry>,
    restore_geometry: bool,
}

impl Default for CompanionWindowState {
    fn default() -> Self {
        Self {
            mode: CompanionMode::Idle,
            always_on_top: false,
            translucent: false,
            min_size: NORMAL_MIN_SIZE,
            normal_geometry_saved: false,
            normal_geometry: None,
            restore_geometry: false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct MonitorBounds {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
struct CompanionSnapshot {
    mode: CompanionMode,
    always_on_top: bool,
    translucent: bool,
    expanded: bool,
}

fn reduce_companion_state(
    previous: CompanionWindowState,
    mode: CompanionMode,
) -> CompanionWindowState {
    let entering_live =
        matches!(previous.mode, CompanionMode::Idle) && !matches!(mode, CompanionMode::Idle);
    let leaving_live =
        !matches!(previous.mode, CompanionMode::Idle) && matches!(mode, CompanionMode::Idle);
    CompanionWindowState {
        mode,
        always_on_top: !matches!(mode, CompanionMode::Idle),
        translucent: matches!(mode, CompanionMode::InGame { .. }),
        min_size: if matches!(mode, CompanionMode::Idle) {
            NORMAL_MIN_SIZE
        } else {
            COMPACT_MIN_SIZE
        },
        normal_geometry_saved: if leaving_live {
            false
        } else {
            previous.normal_geometry_saved || entering_live
        },
        normal_geometry: if leaving_live {
            None
        } else {
            previous.normal_geometry
        },
        restore_geometry: leaving_live,
    }
}

fn clamp_window_position(
    position: (i32, i32),
    size: (u32, u32),
    bounds: MonitorBounds,
) -> (i32, i32) {
    let max_x = bounds
        .x
        .saturating_add(bounds.width.saturating_sub(size.0) as i32);
    let max_y = bounds
        .y
        .saturating_add(bounds.height.saturating_sub(size.1) as i32);
    (
        position.0.clamp(bounds.x, max_x),
        position.1.clamp(bounds.y, max_y),
    )
}

fn scaled_size(size: WindowSize, scale_factor: f64) -> PhysicalSize<u32> {
    PhysicalSize::new(
        (f64::from(size.width) * scale_factor).round().max(1.0) as u32,
        (f64::from(size.height) * scale_factor).round().max(1.0) as u32,
    )
}

fn compact_position(
    bounds: MonitorBounds,
    size: WindowSize,
    scale_factor: f64,
) -> PhysicalPosition<i32> {
    let physical = scaled_size(size, scale_factor);
    let margin = (f64::from(COMPANION_MARGIN) * scale_factor).round() as u32;
    let (x, y) = clamp_window_position(
        (
            bounds
                .x
                .saturating_add(bounds.width.saturating_sub(physical.width + margin) as i32),
            bounds.y.saturating_add(margin as i32),
        ),
        (physical.width, physical.height),
        bounds,
    );
    PhysicalPosition::new(x, y)
}

struct SidecarState(Mutex<SidecarStateInner>, Arc<LifecycleSignal>);
struct CompanionState(Mutex<CompanionWindowState>);

#[derive(Clone, Default)]
struct ShutdownToken(Arc<AtomicBool>);

impl ShutdownToken {
    fn request(&self) {
        self.0.store(true, Ordering::Release);
    }

    fn is_requested(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }
}

struct LifecycleSignal {
    wake: (Mutex<()>, std::sync::Condvar),
    shutdown: ShutdownToken,
}

impl LifecycleSignal {
    fn new() -> Self {
        Self {
            wake: (Mutex::new(()), std::sync::Condvar::new()),
            shutdown: ShutdownToken::default(),
        }
    }

    fn notify(&self) {
        self.wake.1.notify_all();
    }

    fn wait(&self) {
        let guard = self.wake.0.lock().expect("lifecycle signal lock poisoned");
        let _ = self.wake.1.wait_timeout(guard, Duration::from_millis(250));
    }

    fn shutdown(&self) -> ShutdownToken {
        self.shutdown.clone()
    }

    fn request_shutdown(&self) {
        self.shutdown.request();
        self.notify();
    }
}

fn window_error(error: impl std::fmt::Display) -> String {
    error.to_string()
}

fn monitor_bounds<R: tauri::Runtime>(
    window: &tauri::WebviewWindow<R>,
    position: PhysicalPosition<i32>,
    size: PhysicalSize<u32>,
) -> Result<(MonitorBounds, f64), String> {
    let monitor = window.current_monitor().map_err(window_error)?;
    if let Some(monitor) = monitor {
        return Ok((
            MonitorBounds {
                x: monitor.position().x,
                y: monitor.position().y,
                width: monitor.size().width,
                height: monitor.size().height,
            },
            monitor.scale_factor(),
        ));
    }
    Ok((
        MonitorBounds {
            x: position.x,
            y: position.y,
            width: size.width,
            height: size.height,
        },
        window.scale_factor().map_err(window_error)?,
    ))
}

fn capture_geometry<R: tauri::Runtime>(
    window: &tauri::WebviewWindow<R>,
) -> Result<(NormalGeometry, MonitorBounds, f64), String> {
    let position = window.outer_position().map_err(window_error)?;
    let size = window.inner_size().map_err(window_error)?;
    let (bounds, scale_factor) = monitor_bounds(window, position, size)?;
    Ok((
        NormalGeometry {
            position: (position.x, position.y),
            size: WindowSize {
                width: size.width,
                height: size.height,
            },
        },
        bounds,
        scale_factor,
    ))
}

fn companion_snapshot(state: CompanionWindowState) -> CompanionSnapshot {
    CompanionSnapshot {
        mode: state.mode,
        always_on_top: state.always_on_top,
        translucent: state.translucent,
        expanded: matches!(state.mode, CompanionMode::InGame { expanded: true }),
    }
}

#[tauri::command]
fn set_live_companion_mode(
    app: tauri::AppHandle,
    state: tauri::State<'_, CompanionState>,
    mode: CompanionMode,
) -> Result<CompanionSnapshot, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window is unavailable".to_string())?;
    let mut guard = state.0.lock().map_err(window_error)?;
    let previous = *guard;
    let mut next = reduce_companion_state(previous, mode);

    if next.normal_geometry_saved && !previous.normal_geometry_saved {
        let (geometry, _, _) = capture_geometry(&window)?;
        next.normal_geometry = Some(geometry);
    }

    let (bounds, scale_factor) = {
        let position = window.outer_position().map_err(window_error)?;
        let size = window.inner_size().map_err(window_error)?;
        monitor_bounds(&window, position, size)?
    };

    match mode {
        CompanionMode::Idle => {
            window
                .set_min_size(Some(LogicalSize::new(
                    f64::from(NORMAL_MIN_SIZE.width),
                    f64::from(NORMAL_MIN_SIZE.height),
                )))
                .map_err(window_error)?;
            if let Some(geometry) = previous.normal_geometry {
                let restored_size = PhysicalSize::new(geometry.size.width, geometry.size.height);
                let restored_position = clamp_window_position(
                    geometry.position,
                    (restored_size.width, restored_size.height),
                    bounds,
                );
                window.set_size(restored_size).map_err(window_error)?;
                window
                    .set_position(PhysicalPosition::new(
                        restored_position.0,
                        restored_position.1,
                    ))
                    .map_err(window_error)?;
            }
            window.set_decorations(true).map_err(window_error)?;
            window.set_always_on_top(false).map_err(window_error)?;
        }
        CompanionMode::ChampSelect => {
            window
                .set_min_size(Some(LogicalSize::new(
                    f64::from(COMPACT_MIN_SIZE.width),
                    f64::from(COMPACT_MIN_SIZE.height),
                )))
                .map_err(window_error)?;
            let size = scaled_size(CHAMP_SELECT_SIZE, scale_factor);
            window.set_size(size).map_err(window_error)?;
            window
                .set_position(compact_position(bounds, CHAMP_SELECT_SIZE, scale_factor))
                .map_err(window_error)?;
            window.set_decorations(true).map_err(window_error)?;
            // This changes z-order only; deliberately do not call set_focus.
            window.set_always_on_top(true).map_err(window_error)?;
        }
        CompanionMode::InGame { expanded } => {
            window
                .set_min_size(Some(LogicalSize::new(
                    f64::from(COMPACT_MIN_SIZE.width),
                    f64::from(COMPACT_MIN_SIZE.height),
                )))
                .map_err(window_error)?;
            let target_size = if expanded {
                IN_GAME_EXPANDED_SIZE
            } else {
                IN_GAME_SIZE
            };
            window
                .set_size(scaled_size(target_size, scale_factor))
                .map_err(window_error)?;
            if !matches!(
                previous.mode,
                CompanionMode::ChampSelect | CompanionMode::InGame { .. }
            ) {
                window
                    .set_position(compact_position(bounds, target_size, scale_factor))
                    .map_err(window_error)?;
            }
            window.set_decorations(false).map_err(window_error)?;
            window.set_always_on_top(true).map_err(window_error)?;
        }
    }

    if matches!(mode, CompanionMode::Idle) {
        next.normal_geometry = None;
    }
    *guard = next;
    Ok(companion_snapshot(next))
}

struct SidecarStateInner {
    handle: Option<SidecarInfo>,
    startup_error: Option<SidecarStartupError>,
    lifecycle: SidecarLifecycle,
}

#[derive(Debug)]
struct ProcessContainment {
    #[cfg(windows)]
    job: *mut std::ffi::c_void,
}

impl ProcessContainment {
    fn attach(pid: u32) -> Result<Self, String> {
        #[cfg(windows)]
        {
            windows_containment::attach(pid)
        }
        #[cfg(not(windows))]
        {
            let _ = pid;
            Ok(Self {})
        }
    }
}

#[cfg(windows)]
mod windows_containment {
    use super::ProcessContainment;
    use std::ffi::c_void;
    use std::ptr::null_mut;

    type Handle = *mut c_void;
    const PROCESS_TERMINATE: u32 = 0x0001;
    const PROCESS_SET_QUOTA: u32 = 0x0100;
    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: u32 = 9;
    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x2000;

    #[repr(C)]
    struct BasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: u32,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    struct IoCounters {
        read_operations: u64,
        write_operations: u64,
        other_operations: u64,
        read_bytes: u64,
        write_bytes: u64,
        other_bytes: u64,
    }

    #[repr(C)]
    struct ExtendedLimitInformation {
        basic_limit_information: BasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
        fn CloseHandle(handle: Handle) -> i32;
        fn CreateJobObjectW(attributes: *const c_void, name: *const u16) -> Handle;
        fn OpenProcess(access: u32, inherit_handle: i32, process_id: u32) -> Handle;
        fn SetInformationJobObject(
            job: Handle,
            information_class: u32,
            information: *const c_void,
            information_length: u32,
        ) -> i32;
    }

    pub(super) fn attach(pid: u32) -> Result<ProcessContainment, String> {
        unsafe {
            let job = CreateJobObjectW(null_mut(), null_mut());
            if job.is_null() {
                return Err("sidecar containment job creation failed".into());
            }
            let mut limits = ExtendedLimitInformation {
                basic_limit_information: BasicLimitInformation {
                    per_process_user_time_limit: 0,
                    per_job_user_time_limit: 0,
                    limit_flags: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                    minimum_working_set_size: 0,
                    maximum_working_set_size: 0,
                    active_process_limit: 0,
                    affinity: 0,
                    priority_class: 0,
                    scheduling_class: 0,
                },
                io_info: IoCounters {
                    read_operations: 0,
                    write_operations: 0,
                    other_operations: 0,
                    read_bytes: 0,
                    write_bytes: 0,
                    other_bytes: 0,
                },
                process_memory_limit: 0,
                job_memory_limit: 0,
                peak_process_memory_used: 0,
                peak_job_memory_used: 0,
            };
            if SetInformationJobObject(
                job,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                (&mut limits as *mut ExtendedLimitInformation).cast(),
                std::mem::size_of::<ExtendedLimitInformation>() as u32,
            ) == 0
            {
                CloseHandle(job);
                return Err("sidecar containment configuration failed".into());
            }
            let process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
            if process.is_null() {
                CloseHandle(job);
                return Err("sidecar containment process handle failed".into());
            }
            let assigned = AssignProcessToJobObject(job, process);
            CloseHandle(process);
            if assigned == 0 {
                CloseHandle(job);
                return Err("sidecar containment attachment failed".into());
            }
            Ok(ProcessContainment { job })
        }
    }

    pub(super) unsafe fn close(handle: Handle) -> i32 {
        CloseHandle(handle)
    }
}

#[cfg(windows)]
impl Drop for ProcessContainment {
    fn drop(&mut self) {
        unsafe {
            let _ = windows_containment::close(self.job);
        }
    }
}

enum Proc {
    Std(Child),
    Plugin(Option<CommandChild>),
}
impl Proc {
    fn terminate(&mut self) {
        match self {
            Self::Std(child) => {
                let _ = child.kill();
            }
            Self::Plugin(child) => {
                if let Some(child) = child.take() {
                    let _ = child.kill();
                }
            }
        }
    }

    fn reap(&mut self) {
        if let Self::Std(child) = self {
            let _ = child.wait();
        }
    }

    fn kill(&mut self) {
        self.terminate();
        self.reap();
    }
}
enum OutputEvents {
    Lines(Option<mpsc::Receiver<Result<Vec<u8>, String>>>),
}

struct Spawned {
    proc: Proc,
    output: OutputEvents,
    exit: Option<mpsc::Receiver<Result<(), String>>>,
    containment: ProcessContainment,
}
struct SidecarHandle {
    proc: Proc,
    containment: ProcessContainment,
    generation: u64,
    port: u16,
    token: String,
    status: SidecarHealth,
}

impl SidecarHandle {
    fn kill(&mut self) {
        self.proc.kill();
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
enum SidecarHealth {
    Ok,
    Degraded,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SidecarLifecycle {
    NotStarted,
    Starting { generation: u64 },
    Running { generation: u64 },
    Restarting { generation: u64 },
    Failed { generation: u64 },
    Stopping,
}

trait SidecarProcessAdapter {
    type Handle;

    fn spawn(&mut self, token: &str) -> Result<Self::Handle, String>;
    fn wait_for_readiness(
        &mut self,
        child: &mut Self::Handle,
        deadline: Instant,
        shutdown: &ShutdownToken,
    ) -> Result<u16, String>;
    fn wait_for_health(
        &mut self,
        child: &mut Self::Handle,
        port: u16,
        token: &str,
        deadline: Instant,
        shutdown: &ShutdownToken,
    ) -> Result<SidecarHealth, String>;
    fn establish_containment(&mut self, _child: &mut Self::Handle) -> Result<(), String> {
        Ok(())
    }
    fn terminate(&mut self, child: &mut Self::Handle) -> Result<(), String>;
    fn reap(&mut self, child: &mut Self::Handle) -> Result<(), String>;
    fn wait_for_exit(
        &mut self,
        _child: &mut Self::Handle,
        _shutdown: &ShutdownToken,
    ) -> Result<(), String> {
        Err("sidecar exit observation is unavailable".into())
    }
}
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct SidecarStartupError {
    pub code: String,
    pub message: String,
    pub attempts: u8,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct SidecarInfo {
    port: u16,
    token: String,
    status: SidecarHealth,
}

struct SidecarSupervisor<A: SidecarProcessAdapter> {
    adapter: A,
    state: SidecarLifecycle,
    next_generation: u64,
    child: Option<(u64, A::Handle)>,
    info: Option<SidecarInfo>,
    shutdown: ShutdownToken,
}

impl<A: SidecarProcessAdapter> SidecarSupervisor<A> {
    fn new(adapter: A) -> Self {
        Self::with_shutdown(adapter, ShutdownToken::default())
    }

    fn with_shutdown(adapter: A, shutdown: ShutdownToken) -> Self {
        Self {
            adapter,
            state: SidecarLifecycle::NotStarted,
            next_generation: 0,
            child: None,
            info: None,
            shutdown,
        }
    }

    #[allow(dead_code)] // fixture-test seam until #62-#64 wire production callers
    fn state(&self) -> SidecarLifecycle {
        self.state
    }

    #[allow(dead_code)] // fixture-test seam
    fn info(&self) -> Option<SidecarInfo> {
        match self.state {
            SidecarLifecycle::Running { .. } => self.info.clone(),
            _ => None,
        }
    }

    #[allow(dead_code)] // fixture-test seam
    fn adapter(&self) -> &A {
        &self.adapter
    }

    fn start(&mut self, token: String) -> Result<SidecarInfo, SidecarStartupError> {
        if self.shutdown.is_requested()
            || !matches!(
                self.state,
                SidecarLifecycle::NotStarted | SidecarLifecycle::Restarting { .. }
            )
        {
            return Err(self.invalid_transition("sidecar cannot start after shutdown"));
        }
        debug_assert!(self.child.is_none());
        self.next_generation += 1;
        let generation = self.next_generation;
        self.state = SidecarLifecycle::Starting { generation };
        self.info = None;

        let mut child = match self.adapter.spawn(&token) {
            Ok(child) => child,
            Err(message) => return Err(self.fail(generation, message)),
        };
        if let Err(message) = self.adapter.establish_containment(&mut child) {
            let _ = self.adapter.terminate(&mut child);
            let _ = self.adapter.reap(&mut child);
            return Err(self.fail(generation, message));
        }
        if self.child.is_some() {
            let _ = self.adapter.terminate(&mut child);
            let _ = self.adapter.reap(&mut child);
            return Err(self.fail(
                generation,
                "sidecar generation already owns a process".into(),
            ));
        }
        self.child = Some((generation, child));

        let shutdown = self.shutdown.clone();
        let result = (|| {
            let (_, child) = self.child.as_mut().expect("child assigned above");
            let port = self.adapter.wait_for_readiness(
                child,
                Instant::now() + READINESS_TIMEOUT,
                &shutdown,
            )?;
            let status = self.adapter.wait_for_health(
                child,
                port,
                &token,
                Instant::now() + HEALTH_TIMEOUT,
                &shutdown,
            )?;
            Ok(SidecarInfo {
                port,
                token,
                status,
            })
        })();

        match result {
            Ok(info) => {
                if !self.publish_running(generation, info.clone()) {
                    Err(self.fail(
                        generation,
                        "sidecar generation resolution became stale".into(),
                    ))
                } else {
                    Ok(info)
                }
            }
            Err(message) => Err(self.fail(generation, message)),
        }
    }

    fn publish_running(&mut self, generation: u64, info: SidecarInfo) -> bool {
        if self.shutdown.is_requested()
            || self.next_generation != generation
            || !matches!(
                self.state,
                SidecarLifecycle::Starting { generation: current }
                    | SidecarLifecycle::Restarting { generation: current }
                    if current == generation
            )
        {
            return false;
        }
        self.info = Some(info);
        self.state = SidecarLifecycle::Running { generation };
        true
    }

    fn launch(&mut self, token: String) -> Result<SidecarInfo, SidecarStartupError> {
        self.start(token)
    }
    fn restart(&mut self) -> Result<(), SidecarStartupError> {
        if self.shutdown.is_requested() || self.state == SidecarLifecycle::Stopping {
            return Err(self.invalid_transition("stopping sidecar cannot restart"));
        }
        match self.state {
            SidecarLifecycle::Running { generation }
            | SidecarLifecycle::Starting { generation }
            | SidecarLifecycle::Failed { generation } => {
                self.dispose_child()?;
                self.info = None;
                self.state = SidecarLifecycle::Restarting { generation };
                Ok(())
            }
            SidecarLifecycle::NotStarted => Err(self
                .invalid_transition("sidecar cannot restart before its first generation starts")),
            SidecarLifecycle::Restarting { .. } => Ok(()),
            SidecarLifecycle::Stopping => unreachable!("checked above"),
        }
    }

    fn observe_exit(&mut self) -> Result<u64, SidecarStartupError> {
        let generation = match self.state {
            SidecarLifecycle::Running { generation } => generation,
            _ => return Err(self.invalid_transition("sidecar is not running")),
        };
        if self.shutdown.is_requested() {
            self.stop()?;
            return Err(self.stopping_error());
        }
        let Some((owned_generation, mut child)) = self.child.take() else {
            return Err(self.invalid_transition("running sidecar has no process"));
        };
        debug_assert_eq!(generation, owned_generation);
        let observed = self.adapter.wait_for_exit(&mut child, &self.shutdown);
        if self.shutdown.is_requested() {
            let _ = self.adapter.terminate(&mut child);
            let _ = self.adapter.reap(&mut child);
            self.info = None;
            self.state = SidecarLifecycle::Stopping;
            return Err(self.stopping_error());
        }
        observed
            .and_then(|_| self.adapter.reap(&mut child))
            .map_err(|message| self.adapter_error(message))?;
        self.info = None;
        self.state = SidecarLifecycle::Restarting { generation };
        Ok(generation)
    }

    fn stop(&mut self) -> Result<(), SidecarStartupError> {
        self.shutdown.request();
        if self.state == SidecarLifecycle::Stopping {
            return Ok(());
        }
        let result = self.dispose_child();
        self.info = None;
        self.state = SidecarLifecycle::Stopping;
        result
    }

    fn dispose_child(&mut self) -> Result<(), SidecarStartupError> {
        if let Some((_, mut child)) = self.child.take() {
            self.adapter
                .terminate(&mut child)
                .and_then(|_| self.adapter.reap(&mut child))
                .map_err(|message| self.adapter_error(message))?;
        }
        Ok(())
    }

    fn fail(&mut self, generation: u64, message: String) -> SidecarStartupError {
        if let Some((_, mut child)) = self.child.take() {
            let _ = self.adapter.terminate(&mut child);
            let _ = self.adapter.reap(&mut child);
        }
        self.info = None;
        if self.shutdown.is_requested() {
            self.state = SidecarLifecycle::Stopping;
            self.stopping_error()
        } else {
            self.state = SidecarLifecycle::Failed { generation };
            SidecarStartupError {
                code: "sidecar_startup_failed".into(),
                message,
                attempts: 1,
            }
        }
    }

    fn stopping_error(&self) -> SidecarStartupError {
        SidecarStartupError {
            code: "sidecar_startup_failed".into(),
            message: "sidecar is stopping".into(),
            attempts: 0,
        }
    }

    fn invalid_transition(&self, message: &str) -> SidecarStartupError {
        SidecarStartupError {
            code: "sidecar_invalid_transition".into(),
            message: message.into(),
            attempts: 0,
        }
    }

    fn adapter_error(&self, message: String) -> SidecarStartupError {
        SidecarStartupError {
            code: "sidecar_process_error".into(),
            message,
            attempts: 0,
        }
    }

    fn take_running(mut self) -> Result<(A, u64, A::Handle, SidecarInfo), SidecarStartupError> {
        let generation = match self.state {
            SidecarLifecycle::Running { generation } => generation,
            _ => return Err(self.invalid_transition("sidecar is not running")),
        };
        let info = self.info.take().ok_or_else(|| {
            self.invalid_transition("running sidecar did not publish credentials")
        })?;
        let (owned_generation, child) = self
            .child
            .take()
            .ok_or_else(|| self.invalid_transition("running sidecar has no process"))?;
        debug_assert_eq!(generation, owned_generation);
        Ok((self.adapter, generation, child, info))
    }
}

#[allow(dead_code)] // retained for the retry seam removed by #61's cycle
struct LaunchFailure {
    proc: Option<Proc>,
    message: String,
}
#[allow(dead_code)] // superseded by run_startup_cycle; kept as the documented seam
fn retry_launch<F>(mut launch: F) -> Result<SidecarHandle, SidecarStartupError>
where
    F: FnMut() -> Result<SidecarHandle, LaunchFailure>,
{
    let mut last_error = String::from("sidecar did not start");
    for attempt in 1..=MAX_LAUNCHES {
        match launch() {
            Ok(handle) => return Ok(handle),
            Err(mut failure) => {
                if let Some(proc) = failure.proc.as_mut() {
                    proc.kill();
                }
                last_error = failure.message;
            }
        }
        eprintln!("sidecar launch attempt {attempt}/{MAX_LAUNCHES} failed: {last_error}");
    }
    Err(SidecarStartupError {
        code: "sidecar_startup_failed".into(),
        message: last_error,
        attempts: MAX_LAUNCHES,
    })
}
#[tauri::command]
async fn sidecar_info(
    state: tauri::State<'_, SidecarState>,
) -> Result<SidecarInfo, SidecarStartupError> {
    let signal = state.1.clone();
    loop {
        let (lifecycle, info, startup_error) = {
            let snapshot = state.0.lock().map_err(|error| SidecarStartupError {
                code: "sidecar_state_unavailable".into(),
                message: error.to_string(),
                attempts: 0,
            })?;
            (
                snapshot.lifecycle,
                snapshot.handle.clone(),
                snapshot.startup_error.clone(),
            )
        };
        match lifecycle {
            SidecarLifecycle::Running { .. } => {
                return info.ok_or(SidecarStartupError {
                    code: "sidecar_state_unavailable".into(),
                    message: "running sidecar did not publish credentials".into(),
                    attempts: 0,
                });
            }
            SidecarLifecycle::Failed { .. } | SidecarLifecycle::Stopping => {
                return Err(startup_error.unwrap_or(SidecarStartupError {
                    code: "sidecar_startup_failed".into(),
                    message: "sidecar is not running".into(),
                    attempts: 0,
                }));
            }
            SidecarLifecycle::NotStarted
            | SidecarLifecycle::Starting { .. }
            | SidecarLifecycle::Restarting { .. } => {}
        }
        let signal = signal.clone();
        tauri::async_runtime::spawn_blocking(move || signal.wait())
            .await
            .map_err(|error| SidecarStartupError {
                code: "sidecar_state_unavailable".into(),
                message: error.to_string(),
                attempts: 0,
            })?;
    }
}

struct ProductionSidecarAdapter {
    app: tauri::AppHandle,
}

impl SidecarProcessAdapter for ProductionSidecarAdapter {
    type Handle = Spawned;

    fn spawn(&mut self, token: &str) -> Result<Self::Handle, String> {
        if cfg!(debug_assertions) {
            let backend_dir =
                std::env::var("BL_BACKEND_DIR").unwrap_or_else(|_| "../backend".into());
            let launcher = std::env::var("BL_PY_LAUNCHER").unwrap_or_else(|_| "uv".into());
            let mut child = Command::new(launcher)
                .args(["run", "python", "-m", "bhayanak_legends.sidecar"])
                .current_dir(backend_dir)
                .env("BHAYANAK_TOKEN", token)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .map_err(|e| format!("sidecar spawn failed: {e}"))?;
            let containment = match ProcessContainment::attach(child.id()) {
                Ok(containment) => containment,
                Err(error) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(error);
                }
            };
            let stdout = match child.stdout.take() {
                Some(stdout) => stdout,
                None => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err("sidecar stdout was not captured".into());
                }
            };
            let stderr = child.stderr.take();
            let (tx, rx) = mpsc::channel();
            thread::spawn(move || {
                for line in BufReader::new(stdout).lines() {
                    let result = line
                        .map(|line| line.into_bytes())
                        .map_err(|error| error.to_string());
                    if tx.send(result).is_err() {
                        break;
                    }
                }
            });
            if let Some(stderr) = stderr {
                thread::spawn(move || for _ in BufReader::new(stderr).lines() {});
            }
            Ok(Spawned {
                proc: Proc::Std(child),
                output: OutputEvents::Lines(Some(rx)),
                exit: None,
                containment,
            })
        } else {
            let sidecar = self
                .app
                .shell()
                .sidecar("bhayanak-legends-sidecar")
                .map_err(|e| format!("sidecar command unavailable: {e}"))?
                .env("BHAYANAK_TOKEN", token);
            let (mut events, child) = sidecar
                .spawn()
                .map_err(|e| format!("sidecar spawn failed: {e}"))?;
            let containment = match ProcessContainment::attach(child.pid()) {
                Ok(containment) => containment,
                Err(error) => {
                    let _ = child.kill();
                    return Err(error);
                }
            };
            let (tx, rx) = mpsc::channel();
            let (exit_tx, exit_rx) = mpsc::channel();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = events.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            if tx.send(Ok(line)).is_err() {
                                break;
                            }
                        }
                        CommandEvent::Error(error) => {
                            if tx.send(Err(error)).is_err() {
                                break;
                            }
                        }
                        CommandEvent::Terminated(_) => {
                            let _ = tx.send(Err("sidecar exited before readiness".into()));
                            let _ = exit_tx.send(Ok(()));
                            break;
                        }
                        CommandEvent::Stderr(_) => {}
                        _ => {}
                    }
                }
            });
            Ok(Spawned {
                proc: Proc::Plugin(Some(child)),
                output: OutputEvents::Lines(Some(rx)),
                exit: Some(exit_rx),
                containment,
            })
        }
    }
    fn wait_for_readiness(
        &mut self,
        child: &mut Self::Handle,
        deadline: Instant,
        shutdown: &ShutdownToken,
    ) -> Result<u16, String> {
        wait_for_readiness_until(child, deadline, shutdown)
    }

    fn wait_for_health(
        &mut self,
        _child: &mut Self::Handle,
        port: u16,
        token: &str,
        deadline: Instant,
        shutdown: &ShutdownToken,
    ) -> Result<SidecarHealth, String> {
        wait_for_health_until(port, token, deadline, shutdown)
    }

    fn terminate(&mut self, child: &mut Self::Handle) -> Result<(), String> {
        child.proc.terminate();
        Ok(())
    }

    fn reap(&mut self, child: &mut Self::Handle) -> Result<(), String> {
        child.proc.reap();
        Ok(())
    }

    fn wait_for_exit(
        &mut self,
        child: &mut Self::Handle,
        shutdown: &ShutdownToken,
    ) -> Result<(), String> {
        if let Some(events) = child.exit.take() {
            loop {
                if shutdown.is_requested() {
                    return Err("sidecar shutdown requested".into());
                }
                match events.recv_timeout(Duration::from_millis(50)) {
                    Ok(result) => return result.map_err(|error| error),
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                    Err(mpsc::RecvTimeoutError::Disconnected) => {
                        return Err("sidecar exit observer disconnected".into())
                    }
                }
            }
        }
        if let Proc::Std(process) = &mut child.proc {
            loop {
                if process
                    .try_wait()
                    .map_err(|error| format!("sidecar wait failed: {error}"))?
                    .is_some()
                {
                    return Ok(());
                }
                if shutdown.is_requested() {
                    return Err("sidecar shutdown requested".into());
                }
                thread::sleep(Duration::from_millis(50));
            }
        }
        Err("sidecar exit observer unavailable".into())
    }
}

fn sanitize_startup_message(message: String, token: &str) -> String {
    let message = message.replace(token, "[redacted]");
    let mut bounded = message.chars().take(256).collect::<String>();
    if message.chars().count() > 256 {
        bounded.push_str("...");
    }
    bounded
}

fn sleep_with_shutdown(duration: Duration, shutdown: &ShutdownToken) -> bool {
    let deadline = Instant::now() + duration;
    while Instant::now() < deadline {
        if shutdown.is_requested() {
            return false;
        }
        thread::sleep(
            Duration::from_millis(10).min(deadline.saturating_duration_since(Instant::now())),
        );
    }
    !shutdown.is_requested()
}

fn run_startup_cycle<A, F>(
    mut supervisor: SidecarSupervisor<A>,
    mut token_factory: F,
    retry_backoff: Duration,
) -> Result<(A, u64, A::Handle, SidecarInfo), SidecarStartupError>
where
    A: SidecarProcessAdapter,
    F: FnMut() -> String,
{
    let mut last_error = String::from("sidecar did not start");
    for attempt in 1..=MAX_LAUNCHES {
        if attempt > 1 {
            supervisor.restart()?;
        }
        let token = token_factory();
        match supervisor.launch(token.clone()) {
            Ok(_) => return supervisor.take_running(),
            Err(error) => {
                last_error = sanitize_startup_message(error.message, &token);
                eprintln!("sidecar launch attempt {attempt}/{MAX_LAUNCHES} failed: {last_error}");
                if attempt < MAX_LAUNCHES {
                    thread::sleep(retry_backoff);
                }
            }
        }
    }
    Err(SidecarStartupError {
        code: "sidecar_startup_failed".into(),
        message: last_error,
        attempts: MAX_LAUNCHES,
    })
}

fn run_supervised_startup_cycle<A, F>(
    supervisor: &mut SidecarSupervisor<A>,
    mut token_factory: F,
    retry_backoff: Duration,
) -> Result<SidecarInfo, SidecarStartupError>
where
    A: SidecarProcessAdapter,
    F: FnMut() -> String,
{
    let mut last_error = String::from("sidecar did not start");
    for attempt in 1..=MAX_LAUNCHES {
        if attempt > 1 {
            supervisor.restart()?;
        }
        let token = token_factory();
        match supervisor.launch(token.clone()) {
            Ok(info) => return Ok(info),
            Err(error) => {
                last_error = sanitize_startup_message(error.message, &token);
                eprintln!("sidecar launch attempt {attempt}/{MAX_LAUNCHES} failed: {last_error}");
                if attempt < MAX_LAUNCHES {
                    if !sleep_with_shutdown(retry_backoff, &supervisor.shutdown) {
                        return Err(supervisor.stopping_error());
                    }
                }
            }
        }
    }
    Err(SidecarStartupError {
        code: "sidecar_startup_failed".into(),
        message: last_error,
        attempts: MAX_LAUNCHES,
    })
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<SidecarHandle, SidecarStartupError> {
    let supervisor = SidecarSupervisor::new(ProductionSidecarAdapter { app: app.clone() });
    let (_, generation, spawned, info) = run_startup_cycle(
        supervisor,
        || Uuid::new_v4().simple().to_string(),
        STARTUP_RETRY_BACKOFF,
    )?;
    Ok(SidecarHandle {
        proc: spawned.proc,
        containment: spawned.containment,
        generation,
        port: info.port,
        token: info.token,
        status: info.status,
    })
}
fn spawn_output_drain(events: mpsc::Receiver<Result<Vec<u8>, String>>) -> thread::JoinHandle<()> {
    thread::spawn(move || while events.recv().is_ok() {})
}

fn wait_for_readiness_until(
    spawned: &mut Spawned,
    deadline: Instant,
    shutdown: &ShutdownToken,
) -> Result<u16, String> {
    let events = match &mut spawned.output {
        OutputEvents::Lines(events) => events
            .take()
            .ok_or_else(|| "sidecar output consumer already started".to_string())?,
    };
    loop {
        if shutdown.is_requested() {
            return Err("sidecar shutdown requested".into());
        }
        if Instant::now() >= deadline {
            return Err("sidecar readiness timed out".into());
        }
        match events.recv_timeout(Duration::from_millis(50)) {
            Ok(Ok(line)) => {
                let port = parse_readiness(&line)?;
                let _ = spawn_output_drain(events);
                return Ok(port);
            }
            Ok(Err(error)) => return Err(format!("sidecar readiness read failed: {error}")),
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if let Proc::Std(child) = &mut spawned.proc {
                    if child
                        .try_wait()
                        .map_err(|e| format!("sidecar wait failed: {e}"))?
                        .is_some()
                    {
                        return Err("sidecar exited before readiness".into());
                    }
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err("sidecar output closed before readiness".into());
            }
        }
    }
}

fn parse_readiness(line: &[u8]) -> Result<u16, String> {
    let value: Value = serde_json::from_slice(line)
        .map_err(|_| "malformed sidecar readiness output".to_string())?;
    if value.get("type").and_then(Value::as_str) != Some("ready") {
        return Err("unexpected sidecar readiness event".into());
    }
    let port = value
        .get("port")
        .and_then(Value::as_u64)
        .filter(|port| (1..=u16::MAX as u64).contains(port))
        .ok_or_else(|| "sidecar readiness contained an invalid port".to_string())?;
    Ok(port as u16)
}

fn wait_for_health_until(
    port: u16,
    token: &str,
    deadline: Instant,
    shutdown: &ShutdownToken,
) -> Result<SidecarHealth, String> {
    let mut last_error = "sidecar health request failed".to_string();
    while Instant::now() < deadline {
        if shutdown.is_requested() {
            return Err("sidecar shutdown requested".into());
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        match health_request(port, token, remaining.min(Duration::from_millis(500))) {
            Ok(status) => return Ok(status),
            Err(error) => {
                last_error = error;
                let sleep_until = Instant::now() + Duration::from_millis(50);
                while Instant::now() < sleep_until {
                    if shutdown.is_requested() {
                        return Err("sidecar shutdown requested".into());
                    }
                    thread::sleep(Duration::from_millis(10));
                }
            }
        }
    }
    Err(format!("sidecar health timed out: {last_error}"))
}

fn health_request(port: u16, token: &str, timeout: Duration) -> Result<SidecarHealth, String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, timeout)
        .map_err(|e| format!("sidecar health connection failed: {e}"))?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|e| format!("sidecar health timeout setup failed: {e}"))?;
    write!(
        stream,
        "GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-BL-Token: {token}\r\nConnection: close\r\n\r\n"
    )
    .map_err(|e| format!("sidecar health request failed: {e}"))?;
    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|e| format!("sidecar health response failed: {e}"))?;
    parse_health_response(&response)
}

fn parse_health_response(response: &[u8]) -> Result<SidecarHealth, String> {
    let separator = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "malformed sidecar health response".to_string())?;
    let headers = std::str::from_utf8(&response[..separator])
        .map_err(|_| "malformed sidecar health headers".to_string())?;
    let status_line = headers
        .lines()
        .next()
        .ok_or_else(|| "missing sidecar health status".to_string())?;
    let status_code = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or_else(|| "malformed sidecar health status".to_string())?;
    if status_code != 200 {
        return Err(format!("sidecar health returned HTTP {status_code}"));
    }
    let body: Value = serde_json::from_slice(&response[separator + 4..])
        .map_err(|_| "malformed sidecar health body".to_string())?;
    match body.get("status").and_then(Value::as_str) {
        Some("ok") => Ok(SidecarHealth::Ok),
        Some("degraded") => Ok(SidecarHealth::Degraded),
        _ => Err("sidecar health returned an invalid status".into()),
    }
}

fn publish_sidecar_state(
    app: &tauri::AppHandle,
    lifecycle: SidecarLifecycle,
    info: Option<SidecarInfo>,
    startup_error: Option<SidecarStartupError>,
) {
    let state = app.state::<SidecarState>();
    let lock_result = state.0.lock();
    if let Ok(mut guard) = lock_result {
        if guard.lifecycle == SidecarLifecycle::Stopping && lifecycle != SidecarLifecycle::Stopping
        {
            return;
        }
        guard.lifecycle = lifecycle;
        guard.handle = info;
        guard.startup_error = startup_error;
        state.1.notify();
    }
}

fn run_sidecar_supervisor(app: tauri::AppHandle) {
    let shutdown = app.state::<SidecarState>().1.shutdown();
    let mut supervisor =
        SidecarSupervisor::with_shutdown(ProductionSidecarAdapter { app: app.clone() }, shutdown);
    loop {
        if supervisor.shutdown.is_requested() {
            let _ = supervisor.stop();
            publish_sidecar_state(
                &app,
                SidecarLifecycle::Stopping,
                None,
                Some(supervisor.stopping_error()),
            );
            return;
        }
        let generation = supervisor.next_generation + 1;
        publish_sidecar_state(&app, SidecarLifecycle::Starting { generation }, None, None);
        let startup = run_supervised_startup_cycle(
            &mut supervisor,
            || Uuid::new_v4().simple().to_string(),
            STARTUP_RETRY_BACKOFF,
        );
        match startup {
            Ok(info) => {
                let generation = match supervisor.state() {
                    SidecarLifecycle::Running { generation } => generation,
                    _ => return,
                };
                publish_sidecar_state(
                    &app,
                    SidecarLifecycle::Running { generation },
                    Some(info),
                    None,
                );
                if let Err(error) = supervisor.observe_exit() {
                    if supervisor.shutdown.is_requested() {
                        let _ = supervisor.stop();
                        publish_sidecar_state(
                            &app,
                            SidecarLifecycle::Stopping,
                            None,
                            Some(supervisor.stopping_error()),
                        );
                    } else {
                        publish_sidecar_state(
                            &app,
                            SidecarLifecycle::Failed { generation },
                            None,
                            Some(error),
                        );
                    }
                    return;
                }
                publish_sidecar_state(
                    &app,
                    SidecarLifecycle::Restarting { generation },
                    None,
                    None,
                );
            }
            Err(error) => {
                if supervisor.shutdown.is_requested() {
                    let _ = supervisor.stop();
                    publish_sidecar_state(
                        &app,
                        SidecarLifecycle::Stopping,
                        None,
                        Some(supervisor.stopping_error()),
                    );
                } else {
                    let generation = match supervisor.state() {
                        SidecarLifecycle::Failed { generation } => generation,
                        _ => supervisor.next_generation,
                    };
                    publish_sidecar_state(
                        &app,
                        SidecarLifecycle::Failed { generation },
                        None,
                        Some(error),
                    );
                }
                return;
            }
        }
    }
}

fn request_sidecar_shutdown(app: &tauri::AppHandle) {
    let state = app.state::<SidecarState>();
    state.1.request_shutdown();
    if let Ok(mut guard) = state.0.lock() {
        guard.lifecycle = SidecarLifecycle::Stopping;
        guard.handle = None;
        guard.startup_error = Some(SidecarStartupError {
            code: "sidecar_startup_failed".into(),
            message: "sidecar is stopping".into(),
            attempts: 0,
        });
        state.1.notify();
    };
}

fn start_sidecar_supervisor(app: tauri::AppHandle) {
    let worker_app = app.clone();
    let state = app.state::<SidecarState>();
    let lock_result = state.0.lock();
    if let Ok(mut guard) = lock_result {
        guard.lifecycle = SidecarLifecycle::Starting { generation: 1 };
        guard.handle = None;
        guard.startup_error = None;
        state.1.notify();
    }
    tauri::async_runtime::spawn_blocking(move || run_sidecar_supervisor(worker_app));
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState(
            Mutex::new(SidecarStateInner {
                handle: None,
                startup_error: None,
                lifecycle: SidecarLifecycle::NotStarted,
            }),
            std::sync::Arc::new(LifecycleSignal::new()),
        ))
        .setup(|app| {
            start_sidecar_supervisor(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_info,
            set_live_companion_mode
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                request_sidecar_shutdown(&app_handle);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_ephemeral_readiness() {
        assert_eq!(
            parse_readiness(br#"{"type":"ready","port":43217}"#).unwrap(),
            43217
        );
    }

    #[test]
    fn rejects_malformed_readiness() {
        assert!(parse_readiness(br#"{"type":"ready","port":0}"#).is_err());
        assert!(parse_readiness(br#"not-json"#).is_err());
    }

    #[test]
    fn distinguishes_healthy_and_degraded_health() {
        let healthy =
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}";
        let degraded =
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"degraded\"}";
        assert_eq!(parse_health_response(healthy).unwrap(), SidecarHealth::Ok);
        assert_eq!(
            parse_health_response(degraded).unwrap(),
            SidecarHealth::Degraded
        );
    }

    #[test]
    fn startup_retry_budget_is_bounded() {
        let mut attempts = 0;
        let result = retry_launch(|| {
            attempts += 1;
            Err(LaunchFailure {
                proc: None,
                message: "test failure".into(),
            })
        });
        let error = result.err().expect("retry exhaustion should fail");
        assert_eq!(attempts, 3);
        assert_eq!(error.attempts, MAX_LAUNCHES);
    }

    #[test]
    fn detects_early_exit_before_readiness() {
        let (tx, rx) = mpsc::channel();
        tx.send(Err("sidecar exited before readiness".into()))
            .unwrap();
        let mut spawned = Spawned {
            proc: Proc::Plugin(None),
            output: OutputEvents::Lines(Some(rx)),
            exit: None,
            containment: ProcessContainment::attach(0).unwrap(),
        };
        let result = wait_for_readiness_until(
            &mut spawned,
            Instant::now() + Duration::from_secs(1),
            &ShutdownToken::default(),
        );
        assert!(result.unwrap_err().contains("exited before readiness"));
    }

    #[test]
    fn readiness_timeout_is_bounded() {
        let (_tx, rx) = mpsc::channel();
        let mut spawned = Spawned {
            proc: Proc::Plugin(None),
            output: OutputEvents::Lines(Some(rx)),
            exit: None,
            containment: ProcessContainment::attach(0).unwrap(),
        };
        let result = wait_for_readiness_until(
            &mut spawned,
            Instant::now() + Duration::from_millis(1),
            &ShutdownToken::default(),
        );
        assert_eq!(result.unwrap_err(), "sidecar readiness timed out");
    }

    #[test]
    fn health_request_authenticates_without_fixed_port() {
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = Vec::new();
            loop {
                let mut chunk = [0_u8; 256];
                let size = stream.read(&mut chunk).unwrap();
                if size == 0 {
                    break;
                }
                request.extend_from_slice(&chunk[..size]);
                if request.windows(4).any(|window| window == b"\r\n\r\n") {
                    break;
                }
            }
            let request = String::from_utf8_lossy(&request).to_ascii_lowercase();
            assert!(request.contains(&format!("host: 127.0.0.1:{port}")));
            assert!(request.contains("x-bl-token: unit-test-token"));
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n{\"status\":\"degraded\"}")
                .unwrap();
        });

        assert_eq!(
            health_request(port, "unit-test-token", Duration::from_secs(1)).unwrap(),
            SidecarHealth::Degraded
        );
        server.join().unwrap();
    }

    #[test]
    fn companion_transition_replays_idle_champ_select_game_idle() {
        let initial = CompanionWindowState::default();
        let champ_select = reduce_companion_state(initial, CompanionMode::ChampSelect);
        assert_eq!(champ_select.mode, CompanionMode::ChampSelect);
        assert!(champ_select.always_on_top);
        assert!(!champ_select.translucent);
        assert!(champ_select.normal_geometry_saved);
        assert_eq!(champ_select.normal_geometry, None);
        let in_game =
            reduce_companion_state(champ_select, CompanionMode::InGame { expanded: false });
        assert_eq!(in_game.mode, CompanionMode::InGame { expanded: false });
        assert!(in_game.always_on_top);
        assert!(in_game.translucent);
        assert_eq!(in_game.min_size, COMPACT_MIN_SIZE);
        assert!(in_game.normal_geometry_saved);
        let expanded = reduce_companion_state(in_game, CompanionMode::InGame { expanded: true });
        assert_eq!(expanded.mode, CompanionMode::InGame { expanded: true });
        assert!(expanded.always_on_top);
        assert!(expanded.translucent);

        let idle = reduce_companion_state(expanded, CompanionMode::Idle);
        assert_eq!(idle.mode, CompanionMode::Idle);
        assert!(!idle.always_on_top);
        assert!(!idle.translucent);
        assert!(!idle.normal_geometry_saved);
        assert!(idle.restore_geometry);
    }

    #[test]
    fn companion_transition_does_not_overwrite_saved_geometry() {
        let champ_select = reduce_companion_state(
            CompanionWindowState {
                normal_geometry_saved: true,
                ..CompanionWindowState::default()
            },
            CompanionMode::ChampSelect,
        );
        assert!(champ_select.normal_geometry_saved);

        let next = reduce_companion_state(champ_select, CompanionMode::InGame { expanded: false });
        assert!(next.normal_geometry_saved);
    }

    #[test]
    fn bounds_keep_restored_window_reachable() {
        let bounds = MonitorBounds {
            x: 1920,
            y: 0,
            width: 2560,
            height: 1440,
        };
        assert_eq!(
            clamp_window_position((-2000, -500), (1280, 820), bounds),
            (1920, 0)
        );
        assert_eq!(
            clamp_window_position((4300, 900), (1280, 820), bounds),
            (3200, 620)
        );
    }
    #[derive(Default)]
    struct FixtureAdapter {
        events: Vec<&'static str>,
        next_child: u64,
        readiness: Option<u16>,
        readiness_sequence: Vec<u16>,
        health: Option<SidecarHealth>,
        containment_error: Option<String>,
        children: usize,
        terminated: usize,
        descendants_terminated: usize,
        reaped: usize,
        exits: Vec<bool>,
    }

    struct FixtureChild {
        id: u64,
    }

    impl SidecarProcessAdapter for FixtureAdapter {
        type Handle = FixtureChild;

        fn spawn(&mut self, _token: &str) -> Result<Self::Handle, String> {
            self.events.push("spawn");
            self.next_child += 1;
            self.children += 1;
            Ok(FixtureChild {
                id: self.next_child,
            })
        }
        fn establish_containment(&mut self, _child: &mut Self::Handle) -> Result<(), String> {
            self.containment_error.take().map_or(Ok(()), Err)
        }

        fn wait_for_readiness(
            &mut self,
            child: &mut Self::Handle,
            _deadline: Instant,
            _shutdown: &ShutdownToken,
        ) -> Result<u16, String> {
            self.events.push("readiness");
            assert!(child.id > 0);
            self.readiness_sequence
                .pop()
                .or(self.readiness)
                .ok_or_else(|| "not ready".into())
        }

        fn wait_for_health(
            &mut self,
            child: &mut Self::Handle,
            _port: u16,
            _token: &str,
            _deadline: Instant,
            _shutdown: &ShutdownToken,
        ) -> Result<SidecarHealth, String> {
            self.events.push("health");
            assert!(child.id > 0);
            self.health.ok_or_else(|| "not healthy".into())
        }

        fn terminate(&mut self, child: &mut Self::Handle) -> Result<(), String> {
            self.events.push("terminate");
            assert!(child.id > 0);
            self.terminated += 1;
            self.descendants_terminated += 2;
            Ok(())
        }

        fn reap(&mut self, child: &mut Self::Handle) -> Result<(), String> {
            self.events.push("reap");
            assert!(child.id > 0);
            self.reaped += 1;
            Ok(())
        }

        fn wait_for_exit(
            &mut self,
            child: &mut Self::Handle,
            _shutdown: &ShutdownToken,
        ) -> Result<(), String> {
            self.events.push("exit");
            assert!(child.id > 0);
            match self.exits.pop() {
                Some(true) => Ok(()),
                Some(false) | None => Err("fixture child is still running".into()),
            }
        }
    }

    #[test]
    fn lifecycle_publishes_credentials_only_after_authenticated_health() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);

        assert_eq!(supervisor.state(), SidecarLifecycle::NotStarted);
        assert_eq!(supervisor.info(), None);
        let info = supervisor.launch("token-a".into()).unwrap();
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Running { generation: 1 }
        );
        assert_eq!(supervisor.info(), Some(info.clone()));
        assert_eq!(info.port, 43217);
        assert_eq!(info.token, "token-a");
        assert_eq!(
            supervisor.adapter().events,
            vec!["spawn", "readiness", "health"]
        );
    }

    #[test]
    fn lifecycle_rejects_restart_after_stopping_and_rejects_second_child() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        supervisor.launch("token-a".into()).unwrap();
        assert!(supervisor.start("token-b".into()).is_err());
        supervisor.stop().unwrap();
        supervisor.stop().unwrap();
        assert_eq!(supervisor.state(), SidecarLifecycle::Stopping);
        assert!(supervisor.restart().is_err());
        assert!(supervisor.start("token-b".into()).is_err());
        assert_eq!(supervisor.info(), None);
        assert_eq!(supervisor.adapter().children, 1);
        assert_eq!(supervisor.adapter().terminated, 1);
        assert_eq!(supervisor.adapter().reaped, 1);
    }
    #[test]
    fn containment_failure_terminates_attempt_before_publishing() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            containment_error: Some("containment setup failed".into()),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        let error = supervisor.launch("token-a".into()).unwrap_err();
        assert_eq!(error.code, "sidecar_startup_failed");
        assert!(error.message.contains("containment setup failed"));
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Failed { generation: 1 }
        );
        assert_eq!(supervisor.info(), None);
        assert_eq!(supervisor.adapter().children, 1);
        assert_eq!(supervisor.adapter().terminated, 1);
        assert_eq!(supervisor.adapter().reaped, 1);
    }
    #[test]
    fn stopping_terminates_sidecar_tree_and_reaps_root() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        supervisor.launch("token-a".into()).unwrap();
        supervisor.stop().unwrap();
        assert_eq!(supervisor.state(), SidecarLifecycle::Stopping);
        assert_eq!(supervisor.adapter().terminated, 1);
        assert_eq!(supervisor.adapter().descendants_terminated, 2);
        assert_eq!(supervisor.adapter().reaped, 1);
    }
    #[test]
    fn pending_readiness_wait_is_cancelled_without_blocking_shutdown() {
        let (_tx, rx) = mpsc::channel();
        let mut spawned = Spawned {
            proc: Proc::Plugin(None),
            output: OutputEvents::Lines(Some(rx)),
            exit: None,
            containment: ProcessContainment::attach(0).unwrap(),
        };
        let shutdown = ShutdownToken::default();
        let request = shutdown.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(20));
            request.request();
        });
        let started = Instant::now();
        let result =
            wait_for_readiness_until(&mut spawned, started + Duration::from_secs(1), &shutdown);
        assert_eq!(result.unwrap_err(), "sidecar shutdown requested");
        assert!(started.elapsed() < Duration::from_millis(500));
    }
    #[test]
    fn shutdown_wins_race_with_unexpected_exit_without_recovery() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            exits: vec![true],
            ..FixtureAdapter::default()
        };
        let shutdown = ShutdownToken::default();
        let mut supervisor = SidecarSupervisor::with_shutdown(adapter, shutdown.clone());
        supervisor.launch("token-a".into()).unwrap();
        shutdown.request();
        assert!(supervisor.observe_exit().is_err());
        assert_eq!(supervisor.state(), SidecarLifecycle::Stopping);
        assert_eq!(supervisor.info(), None);
        assert_eq!(supervisor.adapter().children, 1);
        assert_eq!(supervisor.adapter().terminated, 1);
        assert_eq!(supervisor.adapter().reaped, 1);
        assert!(supervisor.restart().is_err());
    }

    #[test]
    fn lifecycle_replaces_generation_without_leaking_credentials_or_processes() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        supervisor.launch("token-a".into()).unwrap();
        supervisor.restart().unwrap();
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Restarting { generation: 1 }
        );
        assert_eq!(supervisor.info(), None);
        let info = supervisor.launch("token-b".into()).unwrap();
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Running { generation: 2 }
        );
        assert_eq!(info.token, "token-b");
        assert_eq!(supervisor.adapter().children, 2);
        assert_eq!(supervisor.adapter().terminated, 1);
        assert_eq!(supervisor.adapter().reaped, 1);
    }

    #[test]
    fn lifecycle_exposes_failed_state_without_credentials_and_requires_replacement() {
        let adapter = FixtureAdapter {
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);

        let error = supervisor.launch("token-a".into()).unwrap_err();
        assert_eq!(error.code, "sidecar_startup_failed");
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Failed { generation: 1 }
        );
        assert_eq!(supervisor.adapter().children, 1);
        assert_eq!(supervisor.adapter().terminated, 1);
        assert_eq!(supervisor.adapter().reaped, 1);
        assert!(supervisor.start("token-a-reuse".into()).is_err());
        supervisor.restart().unwrap();
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Restarting { generation: 1 }
        );
        assert_eq!(supervisor.info(), None);
    }

    #[test]
    fn ready_exit_restarts_with_reaped_child_and_fresh_credentials() {
        let adapter = FixtureAdapter {
            readiness_sequence: vec![43218, 43217],
            health: Some(SidecarHealth::Ok),
            exits: vec![true],
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        let first = supervisor.launch("token-a".into()).unwrap();
        assert_eq!(supervisor.observe_exit().unwrap(), 1);
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Restarting { generation: 1 }
        );
        let second =
            run_supervised_startup_cycle(&mut supervisor, || "token-b".into(), Duration::ZERO)
                .unwrap();
        assert_ne!(first.port, second.port);
        assert_ne!(first.token, second.token);
        assert_eq!(
            supervisor.adapter().events,
            vec![
                "spawn",
                "readiness",
                "health",
                "exit",
                "reap",
                "spawn",
                "readiness",
                "health"
            ]
        );
        assert_eq!(supervisor.adapter().children, 2);
        assert_eq!(supervisor.adapter().reaped, 1);
    }

    #[test]
    fn recovery_exhaustion_reports_three_attempts_without_credentials() {
        let adapter = FixtureAdapter {
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        let error =
            run_supervised_startup_cycle(&mut supervisor, || "retry-token".into(), Duration::ZERO)
                .unwrap_err();
        assert_eq!(error.code, "sidecar_startup_failed");
        assert_eq!(error.attempts, MAX_LAUNCHES);
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Failed { generation: 3 }
        );
        assert_eq!(supervisor.info(), None);
        assert_eq!(supervisor.adapter().children, 3);
        assert_eq!(supervisor.adapter().terminated, 3);
        assert_eq!(supervisor.adapter().reaped, 3);
    }

    #[test]
    fn stale_generation_resolution_cannot_overwrite_newer_credentials() {
        let adapter = FixtureAdapter {
            readiness: Some(43217),
            health: Some(SidecarHealth::Ok),
            ..FixtureAdapter::default()
        };
        let mut supervisor = SidecarSupervisor::new(adapter);
        let first = supervisor.launch("token-a".into()).unwrap();
        supervisor.restart().unwrap();
        let second = supervisor.launch("token-b".into()).unwrap();
        assert!(!supervisor.publish_running(1, first));
        assert_eq!(supervisor.info(), Some(second));
        assert_eq!(
            supervisor.state(),
            SidecarLifecycle::Running { generation: 2 }
        );
    }
}
