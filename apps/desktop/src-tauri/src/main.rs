#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// The React frontend talks to client_api_server.py directly over HTTP (see
// src/lib/apiClient.ts). The only Rust commands are for keeping the login
// refresh token in the OS credential store (Windows Credential Manager,
// macOS Keychain, Linux Secret Service) instead of a plaintext file.
use tauri::Manager;

const KEYRING_SERVICE: &str = "com.personalaiassistant.app";
const KEYRING_USER: &str = "refresh_token";

fn entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, KEYRING_USER).map_err(|e| e.to_string())
}

#[tauri::command]
fn load_refresh_token() -> Result<Option<String>, String> {
    match entry()?.get_password() {
        Ok(token) => Ok(Some(token)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
fn save_refresh_token(token: String) -> Result<(), String> {
    entry()?.set_password(&token).map_err(|e| e.to_string())
}

#[tauri::command]
fn clear_refresh_token() -> Result<(), String> {
    match entry()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Older builds kept the whole session (access + refresh token) in a
            // plaintext session.json via tauri-plugin-store - delete it.
            if let Ok(dir) = app.path().app_data_dir() {
                let _ = std::fs::remove_file(dir.join("session.json"));
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_refresh_token,
            save_refresh_token,
            clear_refresh_token
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
