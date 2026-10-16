@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1
  if errorlevel 1 (
    echo Can cai Python 3.12 64-bit tu python.org truoc khi chay.
    pause
    exit /b 1
  )
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Khong tao duoc moi truong. Hay cai Python 3.12 64-bit.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Cai thu vien that bai. Kiem tra ket noi mang va thong bao o tren.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m thanlong --open
if errorlevel 1 pause
