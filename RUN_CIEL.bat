@echo off
title Manas Ciel AI Studio
cd /d "%~dp0"

echo ========================================================
echo   [Wisdom Core] Starting Manas Ciel Portable AI Assistant
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ and check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

cd app
python launch_desktop.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ciel closed with code %ERRORLEVEL%.
    pause
)
