@echo off
chcp 65001 > nul
title 🏭 BTL MẠNG MÁY TÍNH - MÔ PHỎNG VIRTUAL MODBUS RTU SLAVE
color 0b
echo ======================================================================
echo   🏭 ĐANG KHỞI CHẠY CHƯƠNG TRÌNH MÔ PHỎNG SLAVE MODBUS RTU (CNCB0)...
echo ======================================================================
echo.
cd /d "C:\Users\Admin\Desktop\BTLMMT"
node virtual_slave.js
pause
