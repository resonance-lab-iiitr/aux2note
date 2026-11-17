# T021: Lab tab (fifth tab, Ctrl+5)

Capture, analyze and read the verdict without leaving the app.

1. Mount the audio engine in the Audio tab (the START button stays grey and a hint says so until then).
2. Open the **Lab** tab (Ctrl+5). Pick a test type, a duration (5-120 s, default 20) and a label.
   - Silent input: nothing plugged in or the source muted.
   - Test tone (cable out -> in): plug a cable from the output to the input; a 1 kHz tone is played and recorded back.
   - Live source: play music / an instrument into the input.
   - Playback only: tone out, input unplugged (records the block timing).
   Monitoring is switched off during a capture and put back afterwards. The tone is a looping track named LAB TONE; it is removed on STOP (it shows in the Mixer meanwhile).
3. **START CAPTURE**. It stops by itself at the chosen time, or press **STOP**. The folder `captures/<YYYYMMDD_HHMMSS>_<label>/` (next to main.py) holds raw.wav, blocks.csv.gz, meta.json (and output.wav for the tone types).
4. **ANALYZE** works on the selected row (the new capture is selected for you). It runs in the background; the verdict, evidence lines, the next test and report.png (needs matplotlib) appear in the tab. Selecting an older, already analyzed row shows its stored report.
5. **OPEN FOLDER** opens `analysis/` (or the capture folder if not analyzed yet). Attach `analysis/analysis_pack.zip` to a Claude chat.

Table "EARLIER CAPTURES": date, label, type, seconds, analyzed yes/no. REFRESH re-reads the folder.

Screenshot: lab_tab_1366x768.png (tone capture, analyzed).
Not tested on a real card (sandbox has only fake streams): the real PortAudio flags and the tone through a real cable are for T022 / T024.
