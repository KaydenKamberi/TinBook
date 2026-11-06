@echo off
setlocal enabledelayedexpansion

set REPO_ROOT=%~dp0..
cd /d "%REPO_ROOT%"

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
)

:: Create virtual environment if missing
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    call .venv\Scripts\activate
    echo Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate
)

:: Download default voice if missing
set VOICE_FILE=.venv\..\voices\en_US-lessac-medium.onnx
if not exist "%VOICE_FILE%" (
    echo Downloading default voice...
    python scripts\download_voice.py en_US-lessac-medium
    if errorlevel 1 (
        echo Warning: Failed to download voice, but continuing anyway
    )
)

:: Run the app
echo Starting Tinbook...
python -m desktop.app

if errorlevel 1 (
    echo Error: Application exited with error
    pause
    exit /b 1
)
