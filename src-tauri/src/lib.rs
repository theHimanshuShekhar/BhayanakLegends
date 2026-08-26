pub(crate) mod companion;
pub(crate) mod ipc;
mod sidecar;
mod updater;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(updater::init())
        .manage(sidecar::SidecarState::new())
        .manage(companion::CompanionState::new())
        .setup(|app| {
            sidecar::start_supervisor(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            ipc::sidecar_info,
            companion::set_live_mode
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                sidecar::request_shutdown(app_handle);
            }
        });
}
