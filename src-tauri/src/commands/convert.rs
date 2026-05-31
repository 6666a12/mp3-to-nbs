use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use crate::python::runner::{ProgressUpdate, PythonRunner};
use crate::{AppError, AppState};

// ---------------------------------------------------------------------------
// Public data types
// ---------------------------------------------------------------------------

/// Conversion parameters supplied by the React frontend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversionOptions {
    pub source_separation: bool,
    pub quality: String,
}

/// Final conversion result returned to the frontend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversionResult {
    pub output_path: String,
    pub nbs_file_name: String,
    pub tempo: f64,
    pub total_ticks: u64,
    pub note_count: u64,
    pub layer_count: u32,
}

// ---------------------------------------------------------------------------
// Tauri command
// ---------------------------------------------------------------------------

/// Launch the Python converter as a subprocess, stream progress updates via
/// the `conversion-progress` Tauri event, and return the final result.
#[tauri::command]
pub async fn run_local_conversion(
    state: State<'_, AppState>,
    app_handle: AppHandle,
    input_path: String,
    options: ConversionOptions,
) -> Result<ConversionResult, String> {
    // ---- 1. Verify environment is ready -----------------------------------
    let (python_path, _env_status) = {
        let guard = state
            .env_status
            .lock()
            .map_err(|e| e.to_string())?;
        let status = guard.clone();

        if !status.all_ready {
            return Err("Environment not ready. Please run environment check and install missing packages first.".to_string());
        }

        let python = state
            .python_path
            .lock()
            .map_err(|e| e.to_string())?
            .clone()
            .unwrap_or_else(|| "python3".to_string());

        (python, status)
    };

    // ---- 2. Resolve script path and output directory ----------------------
    let runner = PythonRunner::new(Some(python_path), None);
    let script_path = runner.resolve_script("converter.py");

    // Use a temporary directory for intermediate / result files.
    let output_dir = std::env::temp_dir().join("mp3-to-nbs");
    std::fs::create_dir_all(&output_dir)
        .map_err(|e| format!("Failed to create output directory: {}", e))?;

    // ---- 3. Build arguments for converter.py ------------------------------
    let mut args: Vec<String> = Vec::new();
    args.push(input_path.clone());
    args.push("--output-dir".to_string());
    args.push(
        output_dir
            .to_str()
            .ok_or_else(|| "Output directory path is not valid UTF-8".to_string())?
            .to_string(),
    );
    args.push("--source-separation".to_string());
    args.push(options.source_separation.to_string());
    args.push("--quality".to_string());
    args.push(options.quality.clone());

    // ---- 4. Spawn the Python child process --------------------------------
    let mut child = runner
        .spawn_script(&script_path, &args)
        .await
        .map_err(|e| format!("Failed to start converter: {}", e))?;

    let stdout = child.stdout.take().ok_or_else(|| {
        AppError::Io(std::io::Error::new(
            std::io::ErrorKind::Other,
            "Failed to capture stdout",
        ))
        .to_string()
    })?;

    let stderr = child.stderr.take().ok_or_else(|| {
        AppError::Io(std::io::Error::new(
            std::io::ErrorKind::Other,
            "Failed to capture stderr",
        ))
        .to_string()
    })?;

    // ---- 5. Read stdout (progress) and stderr concurrently ----------------
    let app_handle_progress = app_handle.clone();

    let stdout_handle = tokio::spawn(async move {
        PythonRunner::read_progress(stdout, move |update: ProgressUpdate| {
            let _ = app_handle_progress.emit("conversion-progress", &update);
        })
        .await
    });

    let stderr_handle = tokio::spawn(async move {
        PythonRunner::read_stderr(stderr).await
    });

    let (stdout_result, stderr_result) = tokio::join!(stdout_handle, stderr_handle);

    // ---- 6. Wait for the process to exit ----------------------------------
    let exit_status = child
        .wait()
        .await
        .map_err(|e| format!("Converter process error: {}", e))?;

    let stderr_output = stderr_result
        .map_err(|e| format!("Join error (stderr): {}", e))?
        .unwrap_or_default();

    let last_line = stdout_result
        .map_err(|e| format!("Join error (stdout): {}", e))?
        .unwrap_or_default();

    // ---- 7. Check exit status ---------------------------------------------
    if !exit_status.success() {
        return Err(format!(
            "Converter exited with code {:?}\n{}",
            exit_status.code(),
            stderr_output
        ));
    }

    // ---- 8. Parse the final result JSON -----------------------------------
    if last_line.is_empty() {
        return Err("Converter produced no output.".to_string());
    }

    let result: ConversionResult = serde_json::from_str(&last_line)
        .map_err(|e| format!("Failed to parse conversion result: {}", e))?;

    Ok(result)
}
