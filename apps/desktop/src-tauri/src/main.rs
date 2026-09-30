#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// This app has no custom Rust commands - the React frontend talks to
// client_api_server.py directly over HTTP (see src/lib/apiClient.ts). The
// Rust shell here just hosts the webview and the local session-token store.
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::default().build())
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
