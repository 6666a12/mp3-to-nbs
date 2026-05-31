pub mod commands;
pub mod python;

use std::sync::Mutex;

use commands::env::EnvCheckResult;

// ---------------------------------------------------------------------------
// Application-wide error type
// ---------------------------------------------------------------------------

/// Unified error type used throughout the Rust backend.
///
/// All Tauri commands return `Result<T, String>` for serialization, so
/// `AppError` implements `std::fmt::Display` (via `thiserror`) and any
/// place that bubbles up to a command can call `.to_string()`.
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("Python interpreter not found")]
    PythonNotFound,

    #[error("Environment not ready: {0}")]
    EnvNotReady(String),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Subprocess error: {0}")]
    Subprocess(String),

    #[error("{0}")]
    Message(String),
}

// ---------------------------------------------------------------------------
// Global application state
// ---------------------------------------------------------------------------

/// Shared state managed by Tauri and injected into commands via `State<>`.
pub struct AppState {
    /// Cached path to the Python interpreter.
    pub python_path: Mutex<Option<String>>,
    /// Latest environment check snapshot.
    pub env_status: Mutex<EnvCheckResult>,
}

// ---------------------------------------------------------------------------
// Application entry point
// ---------------------------------------------------------------------------

/// Wire up the Tauri app: register plugins, manage state, and bind commands.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Tauri plugins for file dialogs and filesystem access.
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        // Managed state shared across commands.
        .manage(AppState {
            python_path: Mutex::new(None),
            env_status: Mutex::new(EnvCheckResult::default()),
        })
        // Register Tauri commands exposed to the React frontend.
        .invoke_handler(tauri::generate_handler![
            commands::env::check_environment,
            commands::env::install_missing_packages,
            commands::convert::run_local_conversion,
            commands::fs_util::show_in_folder,
            commands::nbt_export::export_nbt,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
