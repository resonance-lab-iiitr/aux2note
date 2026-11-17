# Manual test guide (checklist M1-M13) - Live Looper Pro 2.0 rc6

For a beginner on Windows 10. Do the tests in this order. After each group, send me what is listed under **Send**.
Always: Windows power plan = **High performance**, Windows volume **low**, other programs closed.
Wiring: speakers or headphones on the **green** jack. Instrument on the **blue** jack (never a cable from green to blue except in test 0).
If you hear a loud squeal at any time: untick INPUT LOOPBACK and lower the volume.

## Group A: start, mount, latency, hear yourself (M1, M2, M4 again, M3)

### M1 - the app starts
1. Close any open looper window. Double-click `run_looper.bat` in the rc6 folder (this also tests M13 partly).
2. Expect: a window titled "Live Looper Pro 2.0". At the bottom, the Debug Center Log lists your sound devices ("15 device(s) total ..."), with no red lines.
3. Send: screenshot of the whole window.

### M2 - AUTO and MOUNT (and the power plan warning)
0. Before AUTO, check the **Input Device** box shows the WASAPI **Line In (Realtek High Definition Audio)** and not a webcam microphone. If MOUNT fails with `Invalid sample rate`, choose the WASAPI Line In and WASAPI Speakers by hand and mount again, and tell me.
1. Click **AUTO (recommended)**. Expect the Log line: `AUTO: WASAPI exclusive 48000 Hz / block 128, default devices.`
2. Click **MOUNT AUDIO ENGINE**. Expect: status line `WASAPI EXCL 48000/128 ...`, Log `Trying exclusive 48000/128 ... OK`, button turns red "UNMOUNT AUDIO ENGINE".
3. With High performance on, expect **no** yellow line about the Windows power plan.
4. Power plan warning check: switch Windows to **Balanced** (Power Options), click UNMOUNT, then MOUNT again. Expect a yellow Log line starting `[AUDIO] Windows power plan is 'Balanced'...`. Then switch Windows back to **High performance**, UNMOUNT, MOUNT again, and the warning must not appear.
5. Send: screenshot of the Log after step 2, and one of the Log after the Balanced mount (step 4). Tell me if the warning did NOT appear on Balanced (that would be a bug).

### M4 again - calibrate in this new folder (needed so overdubs line up)
The calibration is saved per folder, so rc6 starts with offset 0.
1. Plug the cable **green jack to blue jack**. Windows volume low.
2. With the engine mounted at 128, click **CALIBRATE LATENCY**, wait about 6 seconds.
3. Expect: a message with Status OK, Round trip about 9.6 ms, 6 of 6 bursts, and the Record offset box filled (about 9.6).
4. Click OK. **Now unplug the cable** and plug your instrument into the blue jack.
5. Send: the round trip number (or a screenshot).

### M3 - you hear yourself
1. Tick **INPUT LOOPBACK**. Play or speak.
2. Expect: you hear yourself with almost no delay, the **IN** meter moves, no crackles.
3. Send: answers to: delay noticeable? crackles? Log red lines? Plus a screenshot while you play.
4. Untick INPUT LOOPBACK afterwards.

## Group B: record, overdub, effects (M5, M6, M7)

### M5 - recording and overdub line up
1. Click **+ ADD TRACK**. Tick **ARM** on that track. Press **RECORD ARMED** (or key R).
2. Play 4 sharp, evenly spaced hits (pick a note hard, or tap the instrument) over about 6 seconds. Press R again to stop.
3. Click **REWIND**. Click **+ ADD TRACK** again. Untick ARM on track 1, tick ARM on track 2.
4. Press **RECORD ARMED**. Track 1 plays; play 4 hits **in time with what you hear**. Stop.
5. Zoom in (**ZOOM +**) and compare the two waveforms.
6. Expect: the loud peaks of track 2 sit directly under the peaks of track 1 (within a few milliseconds when zoomed in), and no empty gap at the start of the take.
7. Send: screenshot of both tracks zoomed in on the first hit, and: did it sound in time?

### M6 - all effects on 4 tracks
1. Make 4 tracks with audio (record or **IMPORT AUDIO**), all unmuted.
2. For each track click **FX** and tick **Enabled** on every tab (EQ, Compressor, Distortion, Delay, Reverb). Click **MASTER FX** and enable all stages too.
3. Press **PLAY** with **LOOP ARRANGEMENT** on. Let it run 2 minutes without touching the PC.
4. Expect: LOAD graph mostly green, CPU % low (about 30 %), xruns 0. At block 128 with every effect on, a rare Log line like `[AUDIO] N block(s) took longer than the block time` is a known result (we measured 6-7 per 10 minutes); it is not a crash. Using the Log **Search** box with `took longer` makes them easy to count.
5. Send: screenshot of the window while it plays, and how many `took longer` lines appeared and how it sounded (clean, rare click, constant crackle).
6. If it crackles a lot: UNMOUNT, set block **256**, MOUNT, and repeat.

### M7 - reverb slider while playing
1. Play a looping track that has the Reverb **Enabled**.
2. In its **FX** window, open the **Reverb** tab and drag **Room Size** slowly left and right while it plays.
3. Expect: the sound changes smoothly, no click or pop, and the reverb tail is not cut off suddenly.
4. Send: what you heard (smooth / click / tail cut).

## Group C: files (M8, M9)

### M8 - save and load
1. Click **SAVE PROJECT**, name it `test1`, save.
2. Click **NEW PROJECT** and confirm. Tracks disappear.
3. Click **OPEN PROJECT** and choose `test1.llproj`.
4. Expect: the same tracks, volumes, effects, and the audio settings show 48000 and block 128. It sounds the same as before.
5. Send: screenshot after loading, and whether the sound and effects matched.

### M9 - export WAV and MP3
1. Click **EXPORT MIX**, choose WAV, save as `mix_test.wav`. Repeat with MP3 as `mix_test.mp3`.
2. Open both in Windows Media Player or another player.
3. Expect: both play and sound like the mix you heard. If the MP3 library is missing, the app saves a WAV and says so in the Log.
4. Send: the Log lines from the export, and whether both files played correctly.

## Group D: problems and diagnostics (M10, M11, M12, M13)

### M10 - the sound card is busy
This checks that a clear message appears instead of a crash.
1. With the first looper window **mounted**, double-click `run_looper.bat` again to open a **second** looper window.
2. In the second window click AUTO, then MOUNT.
3. Expect: a message box "Could not mount audio engine" explaining the devices may be in use, a Log line `No audio mode could be opened ...`, and the window stays open (no crash).
4. Close the second window. Optionally also start a video in a browser while the first window stays mounted: the browser will have no sound (exclusive mode) and the looper keeps running.
5. Send: screenshot of the message and the Log.

### M11 - debug report
1. Click **COPY DEBUG REPORT**.
2. Open Notepad and paste (Ctrl+V).
3. Expect sections: VERSIONS, SETTINGS, ENGINE, TELEMETRY, CALIBRATION, DEVICES, LAST 100 LOG LINES, and a `Power plan:` line under VERSIONS. A file `report_<time>.txt` appears in the `logs` folder.
4. Send: paste the report text into the chat (this also tells me the power plan, calibration and CPU figures).

### M12 - test tone
1. With the engine mounted and Windows volume low, press **F12**. A small bar appears.
2. Choose Sine and press **START**.
3. Expect: a quiet tone from the speakers. **STOP** ends it. Press F12 again to hide the bar.
4. Send: heard the tone? STOP worked?

### M13 - launcher
1. Close the looper. Double-click `run_looper.bat` from the folder (not from a Command Prompt).
2. Expect: the app opens. The black launcher window may stay open behind it; that is fine.
3. The "Python is missing" message cannot be tested without removing Python. Skip it.
4. Send: did it open? If not, send `logs\launcher.log`.
