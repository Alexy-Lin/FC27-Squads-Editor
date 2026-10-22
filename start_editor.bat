@echo off
setlocal
cd /d "%~dp0"

set "FC27_PYTHON="
if exist ".venv\Scripts\python.exe" set "FC27_PYTHON=.venv\Scripts\python.exe"
if not defined FC27_PYTHON if exist "C:\anaconda3\python.exe" set "FC27_PYTHON=C:\anaconda3\python.exe"
if not defined FC27_PYTHON if exist "C:\Python314\python.exe" set "FC27_PYTHON=C:\Python314\python.exe"
if not defined FC27_PYTHON set "FC27_PYTHON=python"

"%FC27_PYTHON%" -c "import flask, waitress, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo Installing Python dependencies...
  "%FC27_PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed. Check Python and network settings.
    pause
    exit /b 1
  )
)

echo Starting FC27 Save Editor...
"%FC27_PYTHON%" web_app.py --open "%~dp0Squads20260918100256149"
pause
