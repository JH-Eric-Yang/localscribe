@echo off
setlocal
rem LocalScribe launcher - double-click me. Everything installs into .managed
cd /d "%~dp0"
set "DIR=%~dp0"

if not exist "%DIR%.managed\logs" mkdir "%DIR%.managed\logs"

echo Starting LocalScribe - leave this window open while you transcribe.

set "UV_PYTHON_INSTALL_DIR=%DIR%.managed\python"
set "UV_CACHE_DIR=%DIR%.managed\uv-cache"
set "HF_HOME=%DIR%.managed\hf-cache"
rem classic HTTP downloads: resumable + stall-recoverable
set "HF_HUB_DISABLE_XET=1"
set "UV=%DIR%.managed\uv\uv.exe"

"%UV%" --version >nul 2>&1
if not errorlevel 1 goto run

if exist "%DIR%.managed\uv" rmdir /s /q "%DIR%.managed\uv"
echo One-time setup: downloading the setup tool...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:UV_UNMANAGED_INSTALL='%DIR%.managed\uv'; irm https://astral.sh/uv/0.11.28/install.ps1 | iex" >>"%DIR%.managed\logs\bootstrap.log" 2>&1
"%UV%" --version >nul 2>&1
if not errorlevel 1 goto run

echo The usual route failed - trying the built-in downloader...
set "UVARCH=x86_64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "UVARCH=aarch64"
if not exist "%DIR%.managed\uv" mkdir "%DIR%.managed\uv"
curl.exe -L -o "%TEMP%\uv.zip" "https://github.com/astral-sh/uv/releases/download/0.11.28/uv-%UVARCH%-pc-windows-msvc.zip" >>"%DIR%.managed\logs\bootstrap.log" 2>&1
tar -xf "%TEMP%\uv.zip" -C "%DIR%.managed\uv" >>"%DIR%.managed\logs\bootstrap.log" 2>&1
"%UV%" --version >nul 2>&1
if errorlevel 1 goto fail

:run
rem GPU mode opt-in: the app creates .managed\gpu-enabled; the cuda extra
rem (nvidia wheels, ~1.5 GB) is downloaded by uv only when it is present.
set "EXTRA="
if exist "%DIR%.managed\gpu-enabled" set "EXTRA=--extra cuda"
"%UV%" run --project "%DIR%." --frozen %EXTRA% python -m app.main
rem Exit code 42 = app asked for a restart (first GPU enable): re-check the
rem flag and run again. "if errorlevel N" is true for exit codes >= N, so
rem test 43 (fail) before 42 (loop) before 1 (fail).
if errorlevel 43 goto fail
if errorlevel 42 goto run
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo Something went wrong - check your internet connection and try again.
echo The universal fix: delete the .managed folder inside this folder, then double-click again.
echo (Technical details: .managed\logs\bootstrap.log)
pause
exit /b 1
