// Tauri IPC commands and shared state access.

use crate::sidecar::{SidecarInfo, SidecarLifecycle, SidecarStartupError, SidecarState};
#[tauri::command]
pub async fn sidecar_info(
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
