@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
rem Usage:  run_soak.bat 128 2      (block size, minutes)   defaults: 256 and 2
set BLOCK=%1
set MINUTES=%2
if "%BLOCK%"=="" set BLOCK=256
if "%MINUTES%"=="" set MINUTES=2
echo Live soak: block %BLOCK%, %MINUTES% minutes. Close other sound apps. Make some noise at the input.
python tools\soak_test.py --live --minutes %MINUTES% --block %BLOCK% > logs\soak_%BLOCK%.txt 2>&1
type logs\soak_%BLOCK%.txt
echo.
echo Saved to %cd%\logs\soak_%BLOCK%.txt
pause
endlocal
