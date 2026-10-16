@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv-ai\Scripts\python.exe" (
  py -3.12 -m venv .venv-ai
  if errorlevel 1 (
    echo Can Python 3.12 64-bit va Python Launcher de chay OCR AI.
    pause
    exit /b 1
  )
)
".venv-ai\Scripts\python.exe" -m pip install -r requirements-ai.txt
if errorlevel 1 (
  echo Cai OCR that bai. Giu thong bao nay de kiem tra; khong bo qua xac minh TLS.
  pause
  exit /b 1
)
echo.
echo GIU CUA SO NAY MO. Hay dong ban cu truoc khi khoi dong may chu OCR.
".venv-ai\Scripts\python.exe" -u -m thanlong --open
echo May chu da dung. Kiem tra thong bao o tren neu co loi.
pause
