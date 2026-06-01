use std::path::PathBuf;
use std::process::Command;

/// Copy a file from src to dst using `std::fs::copy`.
///
/// This bypasses the Tauri fs plugin scope restrictions — unlike the
/// `@tauri-apps/plugin-fs` `copyFile` function, there are no allow-list
/// restrictions on which paths can be read/written.
#[tauri::command]
pub fn copy_file(src: String, dst: String) -> Result<(), String> {
    let src_path = PathBuf::from(&src);
    let dst_path = PathBuf::from(&dst);

    // Ensure the parent directory exists.
    if let Some(parent) = dst_path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create destination directory: {}", e))?;
    }

    std::fs::copy(&src_path, &dst_path)
        .map_err(|e| format!("Failed to copy file: {}", e))?;

    Ok(())
}

/// Reveal the given file or directory in the platform's file manager.
#[tauri::command]
pub fn show_in_folder(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg("/select,")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open Explorer: {}", e))?;
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg("-R")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("Failed to open Finder: {}", e))?;
    }

    #[cfg(target_os = "linux")]
    {
        // Try to open the parent directory
        if let Some(parent) = std::path::Path::new(&path).parent() {
            Command::new("xdg-open")
                .arg(parent)
                .spawn()
                .map_err(|e| format!("Failed to open file manager: {}", e))?;
        }
    }

    Ok(())
}
