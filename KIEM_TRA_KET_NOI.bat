@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>&1
if errorlevel 1 (
  echo Khong tim thay Python Launcher. Hay cai Python 3.12 64-bit.
  pause
  exit /b 1
)
py -3.12 scripts\diagnose_connection.py
echo.
echo Gui tep THONG_TIN_KET_NOI.txt trong thu muc nay de kiem tra loi.
pause
