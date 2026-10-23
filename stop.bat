@echo off
cd /d "%~dp0"
title Stop KodChonLornTone
echo ==================================================
echo Stopping KodChonLornTone processes...
echo ==================================================
taskkill /f /fi "WINDOWTITLE eq KodChonLornTone*" >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
echo All audio engine and server processes stopped.
ping 127.0.0.1 -n 2 >nul
