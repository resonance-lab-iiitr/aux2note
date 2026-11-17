@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo.
echo Live Looper Pro - performance diagnostics (about 5 minutes, no cables needed)
echo Close browsers and music apps first. Do not use the PC while this runs.
echo.
echo [1 of 2] profiling at block 128, garbage collection ON ...
python tools\profile_callback.py --block 128 --minutes 2 > logs\profile_128.txt 2>&1
echo [2 of 2] profiling at block 128, garbage collection OFF ...
python tools\profile_callback.py --block 128 --minutes 2 --nogc > logs\profile_128_nogc.txt 2>&1
echo.
echo Done. Send these two files (or paste their text):
echo    %cd%\logs\profile_128.txt
echo    %cd%\logs\profile_128_nogc.txt
echo.
pause
endlocal
