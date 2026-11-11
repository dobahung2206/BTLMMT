@echo off
chcp 65001 > nul
title CAI DAT TU DONG KHOI DONG SCADA SERVER 24/7
cd /d "%~dp0server_manager"
python server_cli.py install
echo.
pause
