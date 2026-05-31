@echo off
REM ============================================================
REM  MP3-to-NBS Converter — Development Launcher
REM  Starts Vite dev server + Tauri app with correct environment
REM ============================================================

setlocal

REM -- Detect MSYS2 UCRT64 -------------------------------------
if exist "E:\msys2\ucrt64\bin" (
    set "PATH=E:\msys2\ucrt64\bin;E:\msys2\usr\bin;%PATH%"
) else if exist "C:\msys64\ucrt64\bin" (
    set "PATH=C:\msys64\ucrt64\bin;C:\msys64\usr\bin;%PATH%"
)

REM -- Set TMPDIR to Windows format (MinGW GCC needs this) -----
set "TMPDIR=%TEMP%"
set "TMP=%TEMP%"

REM -- Navigate to project root ---------------------------------
cd /d "%~dp0"

echo ============================================================
echo  Step 1/2: Building Rust backend...
echo ============================================================
cd src-tauri
cargo build
if %ERRORLEVEL% neq 0 (
    echo ERROR: cargo build failed
    pause
    exit /b 1
)
cd ..

echo.
echo ============================================================
echo  Step 2/2: Starting Vite ^& Tauri...
echo ============================================================
echo  Vite  : http://localhost:1420
echo  Tauri : GUI window will open shortly
echo ============================================================

start "Vite" cmd /c "npx vite --port 1420"
timeout /t 3 /nobreak >nul
cd src-tauri
cargo run

endlocal
