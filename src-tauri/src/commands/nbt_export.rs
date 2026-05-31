use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tauri::State;

use crate::python::runner::PythonRunner;
use crate::AppState;

// ---------------------------------------------------------------------------
// Public data types
// ---------------------------------------------------------------------------

/// Configuration for the NBS-to-.nbt export.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NbtExportConfig {
    /// Number of blocks between successive ticks along the X axis.
    #[serde(default = "default_spacing")]
    pub spacing: u32,
    /// Minecraft data version (default 3953 = MC 1.21).
    #[serde(default = "default_data_version")]
    pub data_version: i32,
}

fn default_spacing() -> u32 {
    2
}

fn default_data_version() -> i32 {
    3953
}

impl Default for NbtExportConfig {
    fn default() -> Self {
        Self {
            spacing: default_spacing(),
            data_version: default_data_version(),
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri command
// ---------------------------------------------------------------------------

/// Export an NBS file to a Minecraft `.nbt` structure file.
///
/// Calls the `nbt_exporter.py` Python script as a subprocess, passing the NBS
/// path, destination path, and optional configuration.
#[tauri::command]
pub async fn export_nbt(
    state: State<'_, AppState>,
    nbs_path: String,
    output_path: String,
    config: NbtExportConfig,
) -> Result<(), String> {
    // ---- 1. Verify environment --------------------------------------------
    let python_path = {
        let guard = state
            .python_path
            .lock()
            .map_err(|e| e.to_string())?;
        guard
            .clone()
            .unwrap_or_else(|| "python3".to_string())
    };

    // ---- 2. Resolve script path -------------------------------------------
    let runner = PythonRunner::new(Some(python_path), None);
    let script_path = runner.resolve_script("stages/nbt_exporter.py");

    // ---- 3. Build arguments -----------------------------------------------
    let mut args: Vec<String> = Vec::new();
    args.push(nbs_path.clone());
    args.push("--output".to_string());
    args.push(output_path.clone());
    args.push("--spacing".to_string());
    args.push(config.spacing.to_string());
    args.push("--data-version".to_string());
    args.push(config.data_version.to_string());

    // ---- 4. Spawn and wait ------------------------------------------------
    let mut child = runner
        .spawn_script(&script_path, &args)
        .await
        .map_err(|e| format!("Failed to start nbt_exporter: {}", e))?;

    let exit_status = child
        .wait()
        .await
        .map_err(|e| format!("NBT exporter process error: {}", e))?;

    if !exit_status.success() {
        // Collect stderr for a meaningful error message.
        let stderr = child.stderr.take();
        let err_msg = if let Some(stderr) = stderr {
            PythonRunner::read_stderr(stderr)
                .await
                .unwrap_or_else(|e| format!("(failed to read stderr: {})", e))
        } else {
            String::from("(no stderr output)")
        };
        return Err(format!(
            "NBT export failed (exit code {:?}): {}",
            exit_status.code(),
            err_msg,
        ));
    }

    // ---- 5. Verify the output file was created ----------------------------
    let out = PathBuf::from(&output_path);
    if !out.exists() {
        return Err(format!(
            "NBT export completed but output file was not found at: {}",
            output_path
        ));
    }

    Ok(())
}
