use std::net::TcpListener;
use std::process::{Child, Command};
use std::sync::Mutex;

use serde::Serialize;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;
use uuid::Uuid;

struct SidecarState(Mutex<Option<SidecarHandle>>);

enum Proc {
    Std(Child),
    Plugin(Option<CommandChild>),
}

struct SidecarHandle {
    proc: Proc,
    port: u16,
    token: String,
}

impl SidecarHandle {
    fn kill(&mut self) {
        match &mut self.proc {
            Proc::Std(child) => {
                let _ = child.kill();
                let _ = child.wait();
            }
            Proc::Plugin(child) => {
                if let Some(c) = child.take() {
                    let _ = c.kill();
                }
            }
        }
    }
}

#[derive(Serialize)]
pub struct SidecarInfo {
    port: u16,
    token: String,
}

fn find_free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    Ok(listener.local_addr()?.port())
}

#[tauri::command]
fn sidecar_info(state: tauri::State<SidecarState>) -> Result<SidecarInfo, String> {
    let guard = state.0.lock().map_err(|e| e.to_string())?;
    guard
        .as_ref()
        .map(|s| SidecarInfo {
            port: s.port,
            token: s.token.clone(),
        })
        .ok_or_else(|| "sidecar not running".to_string())
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<SidecarHandle, Box<dyn std::error::Error>> {
    let port = find_free_port()?;
    let token = Uuid::new_v4().simple().to_string();

    let proc = if cfg!(debug_assertions) {
        let backend_dir = std::env::var("BL_BACKEND_DIR").unwrap_or_else(|_| "../backend".into());
        let launcher = std::env::var("BL_PY_LAUNCHER").unwrap_or_else(|_| "uv".into());
        let child = Command::new(launcher)
            .args(["run", "python", "-m", "bhayanak_legends.sidecar"])
            .current_dir(backend_dir)
            .env("BHAYANAK_PORT", port.to_string())
            .env("BHAYANAK_TOKEN", &token)
            .spawn()?;
        Proc::Std(child)
    } else {
        let sidecar = app
            .shell()
            .sidecar("bhayanak-legends-sidecar")?
            .env("BHAYANAK_PORT", port.to_string())
            .env("BHAYANAK_TOKEN", &token);
        let (_, child) = sidecar.spawn()?;
        Proc::Plugin(Some(child))
    };

    Ok(SidecarHandle { proc, port, token })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let handle = app.handle().clone();
            match spawn_sidecar(&handle) {
                Ok(handle_proc) => {
                    *handle.state::<SidecarState>().0.lock().unwrap() = Some(handle_proc);
                }
                Err(e) => {
                    eprintln!("sidecar spawn failed: {e}");
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
                    if let Some(handle) = guard.as_mut() {
                        handle.kill();
                    }
                }
            }
        });
}
