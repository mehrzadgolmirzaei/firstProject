@echo off
rem ============================================================
rem  Calculate every equipment in the catalog and write
rem  report + 2D drawing + 3D model for each into the "out" folder.
rem  Extra options can be added, e.g.:  run_all.bat --edition 4
rem                                     run_all.bat --recommended
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed - see start_web.bat & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
".venv\Scripts\python.exe" run.py --all %*
echo.
echo  Done. Files are in the "out" folder.
start "" "%~dp0out"
pause
