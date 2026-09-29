@echo off
rem ============================================================
rem  Foundation design system - web app
rem  Double-click to run. First run installs what is needed.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python is not installed.
  echo  Install Python 3.10 or newer from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" during setup. Then run this file again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  First run: preparing the environment, please wait...
  python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :error
rem OCR for scanned outline PDFs: optional, the app runs without it
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-ocr.txt >nul 2>nul

set FOUNDATION_OPEN_BROWSER=1
cd web
"..\.venv\Scripts\python.exe" server.py
goto :eof

:error
echo.
echo  Setup failed. Check the internet connection and try again.
pause
exit /b 1
