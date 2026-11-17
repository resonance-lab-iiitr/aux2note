@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo.
echo Live Looper Pro - speed experiments (about 7 minutes)
echo Close browsers and music apps. Plug nothing in. Do not use the PC while this runs.
echo You will hear the looped sounds from the speakers: keep Windows volume LOW.
echo.
echo [1 of 6] offline check at block 64 (no sound card) ...
python tools\profile_callback.py --block 64 --minutes 1 > logs\exp_offline64.txt 2>&1
echo [2 of 6] live, baseline ...
python tools\soak_test.py --live --minutes 1 --block 128 > logs\exp_1_baseline.txt 2>&1
echo [3 of 6] live, Python switch interval 0.5 ms ...
python tools\soak_test.py --live --minutes 1 --block 128 --switch-interval 0.0005 > logs\exp_2_switch.txt 2>&1
echo [4 of 6] live, HIGH process priority ...
python tools\soak_test.py --live --minutes 1 --block 128 --priority high > logs\exp_3_priority.txt 2>&1
echo [5 of 6] live, 1 ms Windows timer ...
python tools\soak_test.py --live --minutes 1 --block 128 --timer1 > logs\exp_4_timer.txt 2>&1
echo [6 of 6] live, all three together ...
python tools\soak_test.py --live --minutes 1 --block 128 --switch-interval 0.0005 --priority high --timer1 > logs\exp_5_all.txt 2>&1
echo.
echo ===== SUMMARY =====
for %%F in (logs\exp_1_baseline.txt logs\exp_2_switch.txt logs\exp_3_priority.txt logs\exp_4_timer.txt logs\exp_5_all.txt) do (
  echo --- %%F
  findstr /C:"Tuning" /C:"avg_ms" /C:"max_ms" /C:"cpu_avg_pct" /C:"overruns" /C:"VERDICT" /C:"FAIL:" %%F
)
echo.
echo Send me the text of all files in %cd%\logs that start with exp_
echo (or paste the SUMMARY above plus logs\exp_offline64.txt).
echo.
pause
endlocal
