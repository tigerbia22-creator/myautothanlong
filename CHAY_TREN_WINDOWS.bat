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
echo.
echo GIU CUA SO NAY MO KHI DUNG PHAN MEM. Dong cua so se dung may chu.
echo Neu trang bao Failed to fetch: mo lai tep nay va nhan Ctrl+F5 tren trinh duyet.
".venv\Scripts\python.exe" -u -m thanlong --open
echo.
echo May chu da dung. Neu co loi, giu lai thong bao o tren hoac chay KIEM_TRA_KET_NOI.bat.
pause
