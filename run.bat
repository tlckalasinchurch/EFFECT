@echo off
chcp 65001 >nul
title กดจนหลอนTone Launcher
cd /d "%~dp0"
echo ==================================================
echo ⚡ กดจนหลอนTone - Guitar Rig ^& Amp Workstation
echo    ขับเคลื่อนด้วย Line 6 UX1 Low-Latency Audio Engine
echo ==================================================
.venv\Scripts\python.exe main.py
pause
