// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

pub fn app() -> tauri::App {
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    app().run(|_app_handle, _event| {});
}

#[cfg(test)]
mod tests {
    use super::*;
    use tauri::test::{mock_builder, mock_context, noop_assets};

    #[test]
    fn greet_returns_greeting() {
        assert_eq!(
            greet("Tauri"),
            "Hello, Tauri! You've been greeted from Rust!"
        );
    }

    #[test]
    fn app_builds_and_boots() {
        let app = mock_builder()
            .plugin(tauri_plugin_process::init())
            .plugin(tauri_plugin_updater::Builder::new().build())
            .plugin(tauri_plugin_opener::init())
            .invoke_handler(tauri::generate_handler![greet])
            .build(tauri::generate_context!())
            .expect("app must build and boot with the mock runtime");
        let _handle = app.handle();
    }

    #[test]
    fn updater_config_is_complete() {
        let conf: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json"))
            .expect("tauri.conf.json must be valid JSON");
        let updater = &conf["plugins"]["updater"];
        let pubkey = updater["pubkey"]
            .as_str()
            .expect("updater.pubkey is required for auto-update");
        assert!(!pubkey.is_empty(), "updater.pubkey must not be empty");
        let endpoints = updater["endpoints"]
            .as_array()
            .expect("updater.endpoints is required for auto-update");
        assert!(
            endpoints
                .iter()
                .any(|e| e.as_str().is_some_and(|s| s.starts_with("https://"))),
            "updater needs at least one https endpoint"
        );
    }
}