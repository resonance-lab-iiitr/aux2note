# Run sheet E006 : Latency repeatability on the control paths

For: the owner, on the real PC (Windows 10, Realtek onboard audio). Estimated time: about 5 minutes for the runs, plus 2 minutes for the notes questions. Repeats needed: 5 runs on each of 2 paths (the script does them), plus 1 unplugged run per path.
Card: `experiments/E006_latency_repeatability_on_the_control_pat.md` (its rules are locked; do not "improve" anything while running).

## Before you start
- [ ] Unzip the NEW project zip (PROJECT_v045 or later) into a fresh folder. Open a terminal (cmd or PowerShell) in the folder that contains `CODE` and `RESEARCH`.
- [ ] The Python that runs your looper must have `numpy` and `sounddevice` (the app already needs them).
- [ ] Cable: 3.5 mm stereo, green jack (Speakers / line out) to blue jack (Line In). Same cable as the earlier tests.
- [ ] Windows Sound settings: Line In and Speakers 24 bit 48000 Hz, exclusive mode allowed and "Give exclusive mode applications priority" ticked (as in the earlier tests), "Listen to this device" on Line In OFF, enhancements as they were.
- [ ] Windows volume of Speakers about 50 %. Do NOT change it during the experiment (the script checks the level first and tells you to adjust).
- [ ] Close every other audio program (browser tabs with sound, music, the looper itself, Discord and so on). Power plan: High performance if that is what you normally use; write down what it is.
- [ ] Have these ready, the script asks for them at the end: Realtek driver name and VERSION (Device Manager, Sound controllers, Realtek, Driver tab), the volume %, the formats, the power plan.

## Step 0: test the script itself (10 seconds, no sound)
`python RESEARCH\studies\S001_low_latency_without_crackle\scripts\e006_latency_repeatability_on_the_control_pat.py --selftest`
Expected last line: `SELFTEST PASSED`. If not, copy the whole output into a text file and send it; stop here.

## The experiment (one command; the script does the runs, you do two cable steps)
1. `python RESEARCH\studies\S001_low_latency_without_crackle\scripts\e006_latency_repeatability_on_the_control_pat.py`
2. It prints the devices it chose. Check the names say Line In and Speakers (Realtek), NOT a webcam microphone. If it stops with a "STOP:" message, follow the message (device name part with `--in` / `--out`, or volume).
3. Press Enter when asked, after the cable is plugged in. A throw-away level check runs first (about 8 s). If it says the level is out of range, change the Windows Speakers volume as told and start the command again.
4. The script now runs 5 runs on WASAPI shared and 5 runs on MME (each about 9 s, a new process each time). Do not touch the PC, do not play other sound.
5. When it says "NOW PULL THE CABLE out of the blue Line In jack": pull it out, press Enter. Two short runs follow. They must hear nothing.
6. When it says "PLUG THE CABLE BACK": plug it in, press Enter, and answer the notes questions (write "unknown" if you do not know).
7. It prints a PREVIEW (not the verdict) and writes `results\E006_<label>.zip`. To check the pack: `python RESEARCH\lib\rpack.py check results\E006_<label>.zip` (expect `pack OK`).

## Send back
Attach the latest PROJECT zip and `results\E006_<label>.zip`. Paste:
```
Read START_HERE.md in the attached zip and follow it exactly.
mode: r-analyze
study: S001
exp: E006
```

## If something goes wrong
Stop, do not fix it silently. Put the exact error text (word for word) in a text file, say at which step, and still send the zip if one was made. A run that fails to open a path is a result, not a mistake: keep it.

## Not verified in the sandbox (Claude has no sound card and no Windows)
- The simulated loopback proves the script's steps, the maths of the summary, the fresh-process-per-run routing and the pack format. It does NOT prove: that Windows names the devices as the script expects ("Windows WASAPI", "MME", names containing Line / Speakers), that subprocess runs work on your Python, real signal levels, or that a spread of 1.0 ms is realistic on your card.
- The pass rule needs a spread of the 5 run medians of 1.0 ms or less on at least one path and 3.0 ms or less on both; if your card is looser than that, E006 fails and the next step is to fix the set-up or write a new card, not to change this one.
