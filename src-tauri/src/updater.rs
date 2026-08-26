// Updater plugin composition.

use tauri::Runtime;

pub(crate) fn init<R: Runtime>() -> impl tauri::plugin::Plugin<R> {
    tauri_plugin_updater::Builder::new().build()
}
