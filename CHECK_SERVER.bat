@echo off
chcp 65001 > nul
title KIEM TRA TRANG THAI METAL SORTING SCADA SERVER
cd /d "%~dp0server_manager"
python server_cli.py status
echo.
pause
