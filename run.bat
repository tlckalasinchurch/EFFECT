@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-gpu --disable-gpu-compositing
cd /d "%~dp0"
title KodChonLornTone Launcher
echo ==================================================
echo [KodChonLornTone] Starting Audio Engine and Workstation...
echo Powered by Line 6 UX1 Audio Engine
echo ==================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: .venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe main.py
if %errorlevel% neq 0 (
    echo.
    echo [!] Program closed with error code: %errorlevel%
    pause
)
