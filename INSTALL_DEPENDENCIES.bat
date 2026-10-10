@echo off
title Install Dependencies - Manas Ciel
cd /d "%~dp0"

echo ========================================================
echo   Installing Dependencies for Manas Ciel AI
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo Installing Python packages from app\requirements.txt...
pip install -r app\requirements.txt

echo.
echo ========================================================
echo   [Notice] Dependencies successfully installed!
echo   You can now launch Ciel by double-clicking RUN_CIEL.bat
echo ========================================================
echo.
pause
