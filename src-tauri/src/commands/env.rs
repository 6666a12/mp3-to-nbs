use serde::{Deserialize, Serialize};
use std::io;
use tauri::State;

use crate::python::runner;
use crate::AppState;

// ---------------------------------------------------------------------------
// Public data types (returned to React via Tauri invoke)
// ---------------------------------------------------------------------------

/// Snapshot of the local Python environment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvCheckResult {
    pub python_available: bool,
    pub python_version: Option<String>,
    pub missing_packages: Vec<String>,
    pub all_ready: bool,
}

impl Default for EnvCheckResult {
    fn default() -> Self {
        Self {
            python_available: false,
            python_version: None,
            missing_packages: Vec::new(),
            all_ready: false,
        }
    }
}

/// Outcome of `install_missing_packages`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallResult {
    pub success: bool,
    pub installed: Vec<String>,
    pub remaining: Vec<String>,
}

// ---------------------------------------------------------------------------
// Required Python packages (matching python/requirements.txt)
// ---------------------------------------------------------------------------

const REQUIRED_PACKAGES: &[&str] = &[
    "basic_pitch",
    "librosa",
    "numpy",
    "demucs",
    "pynbs",
    "music21",
    "scipy",
    "pydantic",
    "imageio_ffmpeg",
];

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Check whether Python and all required packages are available.
///
/// Stores the result in `AppState::env_status` so other commands can query it.
#[tauri::command]
pub async fn check_environment(
    state: State<'_, AppState>,
) -> Result<EnvCheckResult, String> {
    let python_cmd = detect_and_store_python(&state).await;

    let result = if let Some(ref py) = python_cmd {
        let (available, missing) = check_packages(py).await?;
        let version = runner::detect_python_version(py);
        let all_ready = available.len() == REQUIRED_PACKAGES.len() && missing.is_empty();
        EnvCheckResult {
            python_available: true,
            python_version: version,
            missing_packages: missing,
            all_ready,
        }
    } else {
        EnvCheckResult {
            python_available: false,
            python_version: None,
            missing_packages: REQUIRED_PACKAGES.iter().map(|p| p.to_string()).collect(),
            all_ready: false,
        }
    };

    // Persist in application state so other commands can read it.
    if let Ok(mut guard) = state.env_status.lock() {
        *guard = result.clone();
    }

    Ok(result)
}

/// Install missing Python packages with `pip install` and re-check the
/// environment afterwards.
#[tauri::command]
pub async fn install_missing_packages(
    state: State<'_, AppState>,
) -> Result<InstallResult, String> {
    // Ensure we have a recent environment snapshot.
    let status = {
        let guard = state.env_status.lock().map_err(|e| e.to_string())?;
        guard.clone()
    };

    if !status.python_available {
        return Err("Python is not installed. Please install Python 3.11+ manually.".to_string());
    }

    let packages_to_install: Vec<String> = status.missing_packages.clone();
    if packages_to_install.is_empty() {
        return Ok(InstallResult {
            success: true,
            installed: vec![],
            remaining: vec![],
        });
    }

    let python = state
        .python_path
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .unwrap_or_else(|| "python3".to_string());

    // Run pip install in a blocking task (it may take a while).
    let py = python.clone();
    let pkgs = packages_to_install.clone();
    let install_result = tokio::task::spawn_blocking(move || {
        run_pip_install(&py, &pkgs)
    })
    .await
    .map_err(|e| format!("Install task panicked: {}", e))?;

    match install_result {
        Ok(()) => {
            // Re-check which packages are still missing.
            let (_available, remaining) = check_packages(&python).await?;
            let installed: Vec<String> = packages_to_install
                .iter()
                .filter(|p| !remaining.contains(p))
                .cloned()
                .collect();

            let result = InstallResult {
                success: remaining.is_empty(),
                installed,
                remaining,
            };

            // Update state.
            if let Ok(mut guard) = state.env_status.lock() {
                guard.missing_packages = result.remaining.clone();
                guard.all_ready = result.success;
            }

            Ok(result)
        }
        Err(e) => Err(format!("pip install failed: {}", e)),
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Detect Python, store the path in `AppState`, and return it.
async fn detect_and_store_python(state: &State<'_, AppState>) -> Option<String> {
    let python = runner::detect_python();
    if let Some(ref py) = python {
        if let Ok(mut guard) = state.python_path.lock() {
            *guard = Some(py.clone());
        }
    }
    python
}

/// Run a Python script snippet that imports every required package and
/// reports `pkg:ok` or `pkg:missing` on stdout.
///
/// Uses `std::process::Command` (blocking) because the check is fast.
async fn check_packages(python: &str) -> Result<(Vec<String>, Vec<String>), String> {
    let script = REQUIRED_PACKAGES
        .iter()
        .map(|p| format!("try:\n import {0}\n print('{0}:ok')\nexcept ImportError:\n print('{0}:missing')", p))
        .collect::<Vec<_>>()
        .join("\n");

    let python = python.to_string();
    let output = tokio::task::spawn_blocking(move || {
        std::process::Command::new(&python)
            .arg("-c")
            .arg(&script)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()
    })
    .await
    .map_err(|e| format!("Package check spawn failed: {}", e))?;

    let output = output.map_err(|e| format!("Failed to run Python for package check: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let _stderr = String::from_utf8_lossy(&output.stderr);

    let mut available: Vec<String> = Vec::new();
    let mut missing: Vec<String> = Vec::new();

    for line in stdout.lines() {
        let trimmed = line.trim();
        if trimmed.ends_with(":ok") {
            available.push(trimmed.trim_end_matches(":ok").to_string());
        } else if trimmed.ends_with(":missing") {
            missing.push(trimmed.trim_end_matches(":missing").to_string());
        }
    }

    // If the Python process failed entirely, treat all packages as missing.
    if !output.status.success() && available.is_empty() && missing.is_empty() {
        missing = REQUIRED_PACKAGES.iter().map(|p| p.to_string()).collect();
    }

    Ok((available, missing))
}

/// Ensure pip is available for the given Python interpreter.
///
/// Runs `python -m ensurepip --default-pip` as a best-effort bootstrap.
/// If pip is already installed this is a no-op; if it isn't, this installs it.
fn ensure_pip(python: &str) {
    let _ = std::process::Command::new(python)
        .arg("-m")
        .arg("ensurepip")
        .arg("--default-pip")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
}

/// Execute `pip install` synchronously.
///
/// Bootstraps pip via `ensurepip` first, then runs the install.
/// Called inside `spawn_blocking` so the async runtime stays responsive.
fn run_pip_install(python: &str, packages: &[String]) -> Result<(), io::Error> {
    // Bootstrap pip if it's missing (best-effort, won't fail if unavailable).
    ensure_pip(python);

    let output = std::process::Command::new(python)
        .arg("-m")
        .arg("pip")
        .arg("install")
        .args(packages)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()?;

    if output.status.success() {
        Ok(())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(io::Error::new(io::ErrorKind::Other, stderr.trim().to_string()))
    }
}
