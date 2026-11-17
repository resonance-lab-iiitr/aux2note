@echo off
setlocal
cd /d "%~dp0"
rem Usage:  run_crackle_matrix.bat --dry-run      (plan and total time, opens nothing)
rem         run_crackle_matrix.bat --quick        (blocks 128 + 256, 48000 Hz, WASAPI + MME)
rem         run_crackle_matrix.bat --scenarios S1,S3 --seconds 20
rem Close browsers and music apps first. Keep Windows volume LOW (the tone plays on the output).
echo Crackle matrix: same captures in every driver, mode, rate and block size.
python tools\crackle_matrix.py %*
echo.
echo Results are in captures\matrix_^<time^>\matrix_summary.md and matrix_summary.csv
pause
endlocal
