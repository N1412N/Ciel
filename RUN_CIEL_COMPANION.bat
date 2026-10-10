@echo off
title Manas Ciel - Companion HUD Overlay
cd /d "%~dp0"
echo ========================================================
echo   MANAS CIEL - COMPANION HUD OVERLAY MODE
echo   Launching compact taskbar companion...
echo ========================================================
start "" python app\launch_desktop.py --companion
exit
