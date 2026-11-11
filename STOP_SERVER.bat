@echo off
chcp 65001 > nul
title DUNG METAL SORTING SCADA SERVER
cd /d "%~dp0server_manager"
python server_cli.py stop
echo.
pause
