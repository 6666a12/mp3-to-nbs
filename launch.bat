@echo off
REM ============================================================
REM  MP3-to-NBS Converter - Development Launcher
REM  Builds frontend + Rust backend, then runs the app.
REM  Uses dist/ directly (no Vite dev server needed).
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
echo  MP3-to-NBS Converter
echo ============================================================

echo.
echo [1/2] Building frontend...
call npm run build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Frontend build failed
    pause
    exit /b 1
)

echo.
echo [2/2] Building and launching Rust backend...
cd src-tauri
cargo run

if %ERRORLEVEL% neq 0 (
    echo ERROR: Application exited with code %ERRORLEVEL%
    cd ..
    pause
    exit /b 1
)

cd ..
endlocal
