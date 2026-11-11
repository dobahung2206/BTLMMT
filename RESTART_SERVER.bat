@echo off
chcp 65001 > nul
title KHOI DONG LAI METAL SORTING SCADA SERVER
cd /d "%~dp0server_manager"
python server_cli.py restart
echo.
pause
