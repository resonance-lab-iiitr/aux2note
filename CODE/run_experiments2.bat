@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo.
echo Live Looper Pro - speed experiments, round 2 (about 6 minutes)
echo Close browsers and music apps. Plug nothing in. Do not use the PC while this runs.
echo You will hear looped sounds from the speakers: keep Windows volume LOW.
echo.
echo [1 of 5] block 64, NO effects (tests the engine itself) ...
python tools\soak_test.py --live --minutes 1 --block 64 --fx none > logs\r2_1_b64_none.txt 2>&1
echo [2 of 5] block 64, typical effects ...
python tools\soak_test.py --live --minutes 1 --block 64 --fx typical > logs\r2_2_b64_typical.txt 2>&1
echo [3 of 5] block 128, typical effects ...
python tools\soak_test.py --live --minutes 1 --block 128 --fx typical > logs\r2_3_b128_typical.txt 2>&1
echo [4 of 5] block 128, ALL effects (new faster reverb + compressor) ...
python tools\soak_test.py --live --minutes 1 --block 128 --fx all > logs\r2_4_b128_all.txt 2>&1
echo [5 of 5] block 128, ALL effects, HIGH priority (fixed) ...
python tools\soak_test.py --live --minutes 1 --block 128 --fx all --priority high > logs\r2_5_b128_all_prio.txt 2>&1
echo.
echo ===== SUMMARY =====
for %%F in (logs\r2_1_b64_none.txt logs\r2_2_b64_typical.txt logs\r2_3_b128_typical.txt logs\r2_4_b128_all.txt logs\r2_5_b128_all_prio.txt) do (
  echo --- %%F
  findstr /C:"Tuning" /C:"avg_ms" /C:"max_ms" /C:"cpu_avg_pct" /C:"overruns       " /C:"VERDICT" /C:"FAIL:" %%F
)
echo.
echo Paste this SUMMARY into the chat.
echo.
pause
endlocal
