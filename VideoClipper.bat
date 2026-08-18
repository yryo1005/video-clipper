@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "PY_VENV=%VENV%\Scripts\python.exe"

if not exist "%PY_VENV%" (
  echo [VideoClipper] Creating virtual environment...
  where py >nul 2>&1
  if %ERRORLEVEL%==0 (
    py -3 -m venv "%VENV%"
  ) else (
    python -m venv "%VENV%"
  )
  if not exist "%PY_VENV%" (
    echo Failed to create .venv. Install Python 3 and try again.
    pause
    exit /b 1
  )
  echo [VideoClipper] Installing packages...
  "%PY_VENV%" -m pip install --upgrade pip
  "%PY_VENV%" -m pip install -r "%ROOT%requirements.txt"
  if errorlevel 1 (
    echo Package install failed.
    pause
    exit /b 1
  )
)

set "PYTHONPATH=%ROOT%src"
"%PY_VENV%" -m videoclipper
if errorlevel 1 (
  echo.
  echo VideoClipper exited with an error.
  pause
)
