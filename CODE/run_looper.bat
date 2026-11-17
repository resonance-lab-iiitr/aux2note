@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

rem ---- 1. Is Python there, and is it 3.10 or newer? ----
python --version >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer. Then run this file again.
  echo Python not found > logs\launcher.log
  pause
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo Your Python is older than 3.10. Please install Python 3.10 or newer.
  python --version > logs\launcher.log 2>&1
  echo Python too old >> logs\launcher.log
  pause
  exit /b 1
)

rem ---- 2. Install the libraries only if something is missing ----
python -c "import sounddevice, numpy, scipy, soundfile" >nul 2>&1
if errorlevel 1 (
  echo Installing the required libraries, one moment...
  python -m pip install sounddevice numpy scipy soundfile
  if errorlevel 1 (
    echo Library install failed. Check your internet connection.
    echo pip install failed > logs\launcher.log
    pause
    exit /b 1
  )
)
rem MP3 export is optional: if this fails the app still works (WAV export only)
python -c "import lameenc" >nul 2>&1
if errorlevel 1 python -m pip install lameenc

rem ---- 3. Start the app ----
python main.py
if errorlevel 1 (
  echo The app stopped with an error. Open the Debug Center or send logs\looper.log
  echo App exited with an error > logs\launcher.log
  pause
)
endlocal
