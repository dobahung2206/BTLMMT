@echo off
chcp 65001 > nul
title GO BO TU DONG KHOI DONG SCADA SERVER
cd /d "%~dp0server_manager"
python server_cli.py uninstall
echo.
pause
