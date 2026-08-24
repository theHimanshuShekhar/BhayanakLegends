use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
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
    let entering_live = matches!(previous.mode, CompanionMode::Idle)
        && !matches!(mode, CompanionMode::Idle);
    let leaving_live = !matches!(previous.mode, CompanionMode::Idle)
        && matches!(mode, CompanionMode::Idle);
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

fn compact_position(bounds: MonitorBounds, size: WindowSize, scale_factor: f64) -> PhysicalPosition<i32> {
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

struct SidecarState(Mutex<SidecarStateInner>);
struct CompanionState(Mutex<CompanionWindowState>);

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
            if !matches!(previous.mode, CompanionMode::ChampSelect | CompanionMode::InGame { .. }) {
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
    handle: Option<SidecarHandle>,
    startup_error: Option<SidecarStartupError>,
}

enum Proc {
    Std(Child),
    Plugin(Option<CommandChild>),
}

impl Proc {
    fn kill(&mut self) {
        match self {
            Self::Std(child) => {
                let _ = child.kill();
                let _ = child.wait();
            }
            Self::Plugin(child) => {
                if let Some(child) = child.take() {
                    let _ = child.kill();
                }
            }
        }
    }
}

enum OutputEvents {
    Lines(mpsc::Receiver<Result<Vec<u8>, String>>),
}

struct Spawned {
    proc: Proc,
    output: OutputEvents,
}
struct SidecarHandle {
    proc: Proc,
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

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct SidecarStartupError {
    pub code: String,
    pub message: String,
    pub attempts: u8,
}

#[derive(Serialize)]
pub struct SidecarInfo {
    port: u16,
    token: String,
    status: SidecarHealth,
}

struct LaunchFailure {
    proc: Option<Proc>,
    message: String,
}
#[tauri::command]
fn sidecar_info(state: tauri::State<SidecarState>) -> Result<SidecarInfo, SidecarStartupError> {
    let guard = state.0.lock().map_err(|e| SidecarStartupError {
        code: "sidecar_state_unavailable".into(),
        message: e.to_string(),
        attempts: 0,
    })?;
    let inner = &*guard;
    if let Some(handle) = inner.handle.as_ref() {
        return Ok(SidecarInfo {
            port: handle.port,
            token: handle.token.clone(),
            status: handle.status,
        });
    }
    Err(inner.startup_error.clone().unwrap_or(SidecarStartupError {
        code: "sidecar_not_running".into(),
        message: "sidecar is not running".into(),
        attempts: 0,
    }))
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<SidecarHandle, SidecarStartupError> {
    retry_launch(|| {
        let token = Uuid::new_v4().simple().to_string();
        launch_once(app, token)
    })
}

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
fn launch_once(app: &tauri::AppHandle, token: String) -> Result<SidecarHandle, LaunchFailure> {
    let mut spawned = if cfg!(debug_assertions) {
        let backend_dir = std::env::var("BL_BACKEND_DIR").unwrap_or_else(|_| "../backend".into());
        let launcher = std::env::var("BL_PY_LAUNCHER").unwrap_or_else(|_| "uv".into());
        let mut child = Command::new(launcher)
            .args(["run", "python", "-m", "bhayanak_legends.sidecar"])
            .current_dir(backend_dir)
            .env("BHAYANAK_TOKEN", &token)
            .stdout(Stdio::piped())
            .spawn()
            .map_err(|e| LaunchFailure {
                proc: None,
                message: format!("sidecar spawn failed: {e}"),
            })?;
        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => {
                return Err(LaunchFailure {
                    proc: Some(Proc::Std(child)),
                    message: "sidecar stdout was not captured".into(),
                })
            }
        };
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
        Spawned {
            proc: Proc::Std(child),
            output: OutputEvents::Lines(rx),
        }
    } else {
        let sidecar = app
            .shell()
            .sidecar("bhayanak-legends-sidecar")
            .map_err(|e| LaunchFailure {
                proc: None,
                message: format!("sidecar command unavailable: {e}"),
            })?
            .env("BHAYANAK_TOKEN", &token);
        let (mut events, child) = sidecar.spawn().map_err(|e| LaunchFailure {
            proc: None,
            message: format!("sidecar spawn failed: {e}"),
        })?;
        let (tx, rx) = mpsc::channel();
        tauri::async_runtime::spawn(async move {
            while let Some(event) = events.recv().await {
                let result = match event {
                    CommandEvent::Stdout(line) => Ok(line),
                    CommandEvent::Error(error) => Err(error),
                    CommandEvent::Terminated(_) => Err("sidecar exited before readiness".into()),
                    CommandEvent::Stderr(_) => continue,
                    _ => continue,
                };
                if tx.send(result).is_err() {
                    break;
                }
            }
        });
        Spawned {
            proc: Proc::Plugin(Some(child)),
            output: OutputEvents::Lines(rx),
        }
    };

    let handshake = (|| {
        let port = wait_for_readiness(&mut spawned)?;
        let status = wait_for_health(port, &token)?;
        Ok((port, status))
    })();
    match handshake {
        Ok((port, status)) => Ok(SidecarHandle {
            proc: spawned.proc,
            port,
            token,
            status,
        }),
        Err(message) => Err(LaunchFailure {
            proc: Some(spawned.proc),
            message,
        }),
    }
}

fn wait_for_readiness(spawned: &mut Spawned) -> Result<u16, String> {
    wait_for_readiness_until(spawned, Instant::now() + READINESS_TIMEOUT)
}

fn wait_for_readiness_until(spawned: &mut Spawned, deadline: Instant) -> Result<u16, String> {
    loop {
        if Instant::now() >= deadline {
            return Err("sidecar readiness timed out".into());
        }
        let OutputEvents::Lines(events) = &mut spawned.output;
        match events.recv_timeout(Duration::from_millis(50)) {
            Ok(Ok(line)) => return parse_readiness(&line),
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
    let value: Value =
        serde_json::from_slice(line).map_err(|_| "malformed sidecar readiness output".to_string())?;
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

fn wait_for_health(port: u16, token: &str) -> Result<SidecarHealth, String> {
    let deadline = Instant::now() + HEALTH_TIMEOUT;
    let mut last_error = "sidecar health request failed".to_string();
    while Instant::now() < deadline {
        let remaining = deadline.saturating_duration_since(Instant::now());
        match health_request(port, token, remaining.min(Duration::from_millis(500))) {
            Ok(status) => return Ok(status),
            Err(error) => {
                last_error = error;
                thread::sleep(Duration::from_millis(50));
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
        "GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nX-BL-Token: {token}\r\nConnection: close\r\n\r\n"
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(SidecarState(Mutex::new(SidecarStateInner {
            handle: None,
            startup_error: None,
        })))
        .plugin(tauri_plugin_shell::init())
        .manage(CompanionState(Mutex::new(CompanionWindowState::default())))
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let handle = app.handle().clone();
            let state = handle.state::<SidecarState>();
            match spawn_sidecar(&handle) {
                Ok(sidecar) => {
                    if let Ok(mut guard) = state.0.lock() {
                        guard.handle = Some(sidecar);
                        guard.startup_error = None;
                    }
                }
                Err(error) => {
                    eprintln!("sidecar startup failed: {}", error.message);
                    if let Ok(mut guard) = state.0.lock() {
                        guard.startup_error = Some(error);
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_info, set_live_companion_mode])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                if let Ok(mut guard) = app_handle.state::<SidecarState>().0.lock() {
                    if let Some(handle) = guard.handle.as_mut() {
                        handle.kill();
                    }
                    guard.handle = None;
                }
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
        let healthy = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}";
        let degraded =
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"degraded\"}";
        assert_eq!(parse_health_response(healthy).unwrap(), SidecarHealth::Ok);
        assert_eq!(parse_health_response(degraded).unwrap(), SidecarHealth::Degraded);
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
        tx.send(Err("sidecar exited before readiness".into())).unwrap();
        let mut spawned = Spawned {
            proc: Proc::Plugin(None),
            output: OutputEvents::Lines(rx),
        };
        let result = wait_for_readiness_until(&mut spawned, Instant::now() + Duration::from_secs(1));
        assert!(result.unwrap_err().contains("exited before readiness"));
    }

    #[test]
    fn readiness_timeout_is_bounded() {
        let (_tx, rx) = mpsc::channel();
        let mut spawned = Spawned {
            proc: Proc::Plugin(None),
            output: OutputEvents::Lines(rx),
        };
        let result = wait_for_readiness_until(&mut spawned, Instant::now() + Duration::from_millis(1));
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
            assert!(request.contains("x-bl-token: unit-test-token"));
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n{\"status\":\"degraded\"}",
                )
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
        let in_game = reduce_companion_state(champ_select, CompanionMode::InGame { expanded: false });
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
}
