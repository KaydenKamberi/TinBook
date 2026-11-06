@echo off
setlocal

rem Tinbook launcher for Windows. Double-click it, or run it from any folder.
rem It always works from the repo root (this file lives in scripts\).
cd /d "%~dp0.."

python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH.
    pause
    exit /b 1
)

rem Create the virtual environment if it is missing or incomplete.
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

rem Install dependencies when they changed since the last successful install.
rem The marker is a copy of requirements.txt, written only after pip succeeds,
rem so a failed install is retried next run and new requirements get installed.
set NEED_INSTALL=0
if not exist ".venv\.installed" set NEED_INSTALL=1
if exist ".venv\.installed" (
    fc /b requirements.txt ".venv\.installed" >nul 2>&1
    if errorlevel 1 set NEED_INSTALL=1
)
if "%NEED_INSTALL%"=="1" (
    echo Installing dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install dependencies. Run this script again to retry.
        pause
        exit /b 1
    )
    copy /y requirements.txt ".venv\.installed" >nul
)

rem Download the default voice if it is missing.
if not exist "voices\en_US-lessac-medium.onnx" (
    echo Downloading default voice...
    python scripts\download_voice.py en_US-lessac-medium
    if errorlevel 1 echo Warning: Failed to download the voice. Continuing anyway.
)

echo Starting Tinbook...
python -m desktop.app
if errorlevel 1 (
    echo Error: Tinbook exited with an error.
    pause
    exit /b 1
)
