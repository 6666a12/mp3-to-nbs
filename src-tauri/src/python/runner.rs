use std::io;
use std::path::{Path, PathBuf};
use std::process::Stdio;

use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, ChildStderr, ChildStdout, Command};

/// A lightweight progress update emitted by the Python converter during processing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProgressUpdate {
    pub step: String,
    pub progress: f64,
    pub message: String,
}

/// Manages the lifecycle of a local Python subprocess.
///
/// Uses `tokio::process::Command` so that long-running scripts (conversion)
/// run asynchronously without blocking the Tauri command thread pool.
pub struct PythonRunner {
    /// Path (or command name) of the Python interpreter, e.g. `python3`.
    pub python_path: String,
    /// Base directory containing Python scripts (`converter.py`, `nbt_exporter.py`, …).
    pub scripts_dir: PathBuf,
}

impl PythonRunner {
    /// Create a new runner.
    ///
    /// If `python_path` is `None` the constructor auto-detects the interpreter.
    /// `scripts_dir` defaults to `./python` when `None`, with fallback walking
    /// up from the executable to find the project root.
    pub fn new(python_path: Option<String>, scripts_dir: Option<PathBuf>) -> Self {
        let python_path = python_path.or_else(detect_python).unwrap_or_else(|| "python3".to_string());
        let scripts_dir = scripts_dir.unwrap_or_else(|| find_scripts_dir());
        Self {
            python_path,
            scripts_dir,
        }
    }

    /// Return the absolute path to a named script inside `scripts_dir`.
    pub fn resolve_script(&self, name: &str) -> PathBuf {
        self.scripts_dir.join(name)
    }

    /// Spawn a Python script as an asynchronous child process.
    ///
    /// `script_path` should be the full path to the `.py` file.  Stdout and
    /// stderr are both piped so the caller can consume progress lines and
    /// capture error output.
    pub async fn spawn_script(
        &self,
        script_path: &Path,
        args: &[String],
    ) -> io::Result<Child> {
        Command::new(&self.python_path)
            .arg(script_path)
            .args(args)
            // Use legacy decoders to avoid torchcodec/FFmpeg DLL dependency
            .env("TORCHAUDIO_USE_LEGACY_DECODERS", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
    }

    /// Read progress lines from the child's stdout.
    ///
    /// Every non-empty line is parsed as a `ProgressUpdate`.  When parsing
    /// succeeds `on_progress` is called so the caller can relay the update to
    /// the UI (e.g. via a Tauri event).  Lines that do not parse as progress
    /// are assumed to be the final result payload; the method returns the
    /// **last** such line.
    ///
    /// This is intentionally an associated function (no `&self`) so it can be
    /// called inside a `tokio::spawn` without borrowing `self`.
    pub async fn read_progress<F>(stdout: ChildStdout, mut on_progress: F) -> io::Result<String>
    where
        F: FnMut(ProgressUpdate) + Send + 'static,
    {
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();
        let mut last_result_line = String::new();

        while let Some(line) = lines.next_line().await? {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            if let Ok(progress) = serde_json::from_str::<ProgressUpdate>(trimmed) {
                on_progress(progress);
            } else {
                // Did not parse as progress — treat as a potential final result.
                last_result_line = trimmed.to_string();
            }
        }

        Ok(last_result_line)
    }

    /// Read stderr to a string (convenience helper).
    pub async fn read_stderr(stderr: ChildStderr) -> io::Result<String> {
        let mut reader = BufReader::new(stderr);
        let mut buf = String::new();
        tokio::io::AsyncReadExt::read_to_string(&mut reader, &mut buf).await?;
        Ok(buf)
    }
}

// ---------------------------------------------------------------------------
// Auto-detection helpers
// ---------------------------------------------------------------------------

/// Try to locate a working Python interpreter.
///
/// Search order (venv first — it's more likely to have pip available):
/// 1. `.venv/Scripts/python.exe` walking up from CWD.
/// 2. `.venv/Scripts/python.exe` walking up from the executable.
/// 3. `python3` / `python` on PATH (fallback).
pub fn detect_python() -> Option<String> {
    // ---- Walk up from CWD and exe looking for .venv FIRST --------------------
    // Venv Python is preferred because it should have pip bootstrapped.
    let search_roots: Vec<Option<PathBuf>> = vec![
        std::env::current_dir().ok(),
        std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.to_path_buf())),
    ];

    for root in search_roots.iter().flatten() {
        for ancestor in root.ancestors().take(8) {
            let candidate = ancestor.join(".venv/Scripts/python.exe");
            if candidate.exists() {
                return Some(candidate.to_string_lossy().to_string());
            }
        }
    }

    // ---- PATH-based fallback -------------------------------------------------
    for candidate in &["python3", "python"] {
        if let Ok(output) = std::process::Command::new(candidate)
            .arg("--version")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()
        {
            if output.status.success() {
                return Some(candidate.to_string());
            }
        }
    }

    None
}

/// Locate the `python/` scripts directory by walking up from CWD and the
/// executable location.
fn find_scripts_dir() -> PathBuf {
    let cwd = PathBuf::from("python");
    if cwd.exists() && cwd.is_dir() {
        return cwd;
    }

    let search_roots: Vec<Option<PathBuf>> = vec![
        std::env::current_dir().ok(),
        std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.to_path_buf())),
    ];

    for root in search_roots.iter().flatten() {
        for ancestor in root.ancestors().take(8) {
            let candidate = ancestor.join("python");
            if candidate.exists() && candidate.is_dir() {
                return candidate;
            }
        }
    }

    // Last resort: return CWD-relative path
    cwd
}

/// Return the Python version string (e.g. "Python 3.11.9") by running
/// `python --version`.  Uses `std::process::Command` because this is a
/// quick, fire-and-forget check.
pub fn detect_python_version(python: &str) -> Option<String> {
    let output = std::process::Command::new(python)
        .arg("--version")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()
        .ok()?;

    if output.status.success() {
        // --version writes to stdout on Unix, stderr on some Windows builds.
        let raw = String::from_utf8_lossy(
            if output.stdout.is_empty() {
                &output.stderr
            } else {
                &output.stdout
            }
        );
        Some(raw.trim().to_string())
    } else {
        None
    }
}
