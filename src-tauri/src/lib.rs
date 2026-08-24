use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use uuid::Uuid;

const MAX_LAUNCHES: u8 = 3;
const READINESS_TIMEOUT: Duration = Duration::from_secs(5);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(5);

struct SidecarState(Mutex<SidecarStateInner>);

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
        .invoke_handler(tauri::generate_handler![sidecar_info])
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
}
