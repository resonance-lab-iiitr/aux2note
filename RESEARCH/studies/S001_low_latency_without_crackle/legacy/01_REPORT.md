# Crackle Lab: real-PC test report v2 (sessions 1 and 2, 2026-11-12)

Project: Live Looper Pro (code of project zip v036; the owner runs the v032 copy in `D:\PROJECT_v032\PROJECT\CODE`, Python 3.10, Windows 10 10.0.19041.1)
Tester: the project owner. Analysis: Claude, from the files, logs and pasted output the tester provided.
Status: T024 (findings) finished. The fault is located to the WASAPI exclusive path; its exact cause is not known. Report v1 is kept unchanged as `01a_REPORT_session1_ORIGINAL_unchanged.md`; this v2 replaces its conclusions where they differ (see section 8).

---------------------------------------------------------------------------
## 1. Goal and where we stand

Owner's goal: round-trip latency of 10 to 20 ms or lower, with no crackle and no other disturbance. The crackle question was investigated first because a low-latency mode is only useful if it is clean.

Where we stand:
1. **Clean modes found:** WASAPI shared and MME were clean in 5 of 5 tone-loopback captures. They are the slow modes (the program's own log text says shared mode has about 37 ms round trip; latency was not measured by us).
2. **The fast mode is faulty:** WASAPI exclusive (the mode that can reach low latency) gave damaged recordings in 3 of 4 captures.
3. **Not the program's sound:** in the new captures the engine's own output (`output.wav`) is a perfect tone in all three runs, including the run whose input recording is badly damaged. The fault therefore enters after the engine's output buffer (exclusive-path driver, sound card, analog loop, or capture side). It cannot yet be split further.
4. **Not CPU or timing:** 0 late blocks, 0 PortAudio status flags during the captures; callback time 0.08 to 0.45 ms against a 2.7 ms (128) or 5.3 ms (256) block.
5. **Intermittent:** exclusive 128 was bad once (143 bursts/s) and clean once; exclusive 256 was bad twice.
6. **Next:** see `04_RESEARCH_DIRECTION_low_latency.md`.

---------------------------------------------------------------------------
## 2. Test environment (known and unknown)

Known: Realtek High Definition Audio onboard; NVIDIA HDMI audio (not plugged in); webcam microphone "ZQ-1080RL HD Camera" (USB); ASIO4ALL v2 installed. One 3.5 mm stereo cable from the green jack (line out) to the blue jack (line in), as stated by the owner. After the cable was connected Realtek Line In became the default input; Line In and Speakers both 24 bit / 48000 Hz; exclusive control allowed and "Give exclusive mode applications priority" ticked; "Listen to this device" off (screenshots in `evidence/session1_original_files/screenshots/`).
Device list from the app log (`logs/looper_2026-11-12.log`, 14:39:07), WASAPI entries: ID 11 Speakers (Realtek) out 48000 Hz default; ID 12 Microphone (ZQ-1080RL HD Camera) in 16000 Hz; ID 13 Line In (Realtek) in 48000 Hz default. Also listed: MME, DirectSound, WDM-KS entries and `ID 10 ASIO | ASIO4ALL v2` (2 in, 8 out).
All captures: 48000 Hz, 1 input channel opened by the program, effects off, monitoring off, 20 s. The Lab captures used the test tone 1000 Hz, level 0.3, with output capture on.
Not known: Windows volume level, Realtek driver version, whether crackle was audible in the program, what else was running, formats before the first screenshot. The owner's `notes.txt` was not supplied.

---------------------------------------------------------------------------
## 3. Chronology

Session 1 (matrix tool, from report v1; times of the screenshots 14:21 to 14:24):
1. Install check (`--dry-run`, `--help`): ok.
2. S1 silence, quick matrix, nothing in the input: 4 WASAPI runs `open_failed` (`Invalid sample rate [PaErrorCode -9997]`); 2 MME runs ok.
3. Windows Sound screenshots: webcam microphone was the default input; both Realtek inputs "not plugged in".
4. Cable green to blue; Line In became default; formats 24 bit / 48000 Hz.
5. S3 tone loopback, quick matrix: 6 runs ok.

Session 2 (Lab tab, times from `looper.log`):
| Time | Event |
|---|---|
| 14:39:07 | App start; device inventory printed |
| 14:40:04 | Exclusive 48000/128 mounted ok (Line In + Speakers) |
| 14:40:26 | Two GUI errors in the mouse-wheel handler (`scroll_frame.py` line 58 via 68); audio not affected; task T029, fixed in project v036 |
| 14:42:17 to 14:42:37 | Capture excl128 (2 min 13 s after the mount) |
| 14:42:42 to :43 | 8 late-block warnings, worst 447 % (after the capture stopped, during ANALYZE) |
| 14:43:26 | Unmount |
| 14:43:35 to 14:44:06 | Exclusive 256 mounted, no capture, unmounted |
| 14:44:08 | Exclusive 256 mounted again |
| 14:44:15 to 14:44:35 | Capture excl256 (7 s after the mount) |
| 14:44:40 to :43 | 4 late-block warnings, worst 227 % (ANALYZE) |
| 14:45:09 | Unmount |
| 14:45:13 | Shared 48000/256 mounted; log says about 37 ms round trip expected |
| 14:45:33 to 14:45:53 | Capture shared256 |
| 14:45:59 | 2 late-block warnings, worst 113 % (ANALYZE) |
| 14:51:35 | Ctrl+C in the console, logged as CRIT with an empty message |
Console: a matplotlib warning `No artists with labels found to put in legend` (`crackle_report.py` line 463).

---------------------------------------------------------------------------
## 4. Results

### 4.1 S3 tone loopback, all runs (48000 Hz, 20 s)
"Tone error" = rms of the residual against a fitted 1 kHz sine, relative to the tone (about -62 dB is clean). "Bursts per s": session 1 values from report v1; session 2 values from `analysis/analysis_output_lab_captures.txt` (bad samples with residual above 0.02, joined when closer than 20 samples). The two counting methods differ a little: compare modes, not decimals.

| Session | Mode | Block | raw tone error | Bursts per s | Tool clicks/min | output.wav | Late blocks / status flags |
|---|---|---|---|---|---|---|---|
| 1 | MME | 128 | -62.7 dB | 0 | 2.99 | not captured | 0 / 0 |
| 1 | MME | 256 | -62.5 dB | 0 | 2.99 | not captured | 0 / 0 |
| 1 | WASAPI shared | 128 | -62.4 dB | 0 | 8.96 | not captured | 0 / 0 |
| 1 | WASAPI shared | 256 | -61.7 dB | 0 | 8.97 | not captured | 0 / 0 |
| 1 | WASAPI exclusive | 128 | -8.8 dB | 143 | 8796 | not captured | 0 / 0 |
| 1 | WASAPI exclusive | 256 | -5.2 dB | 87 | 5278 | not captured | 0 / 0 |
| 2 | WASAPI exclusive | 128 | **-60.7 dB** | **0** | 0.0 | clean | 0 / 0 |
| 2 | WASAPI exclusive | 256 | **-10.2 dB** | **72.7** (1382 bursts) | 6009 (2003 clicks) | clean | 0 / 0 |
| 2 | WASAPI shared | 256 | -61.5 dB | 0 | 3.0 (1 event at tone onset) | clean | 0 / 0 |

output.wav in all three session 2 runs: peak exactly 0.3000, both channels, tone error -152.5 dB (a mathematically perfect sine).

### 4.2 Shape of the damage (excl256, session 2)
- 1382 bursts in 19 s; median gap 9.0 ms; median width 19 samples (about 0.4 ms); largest residual 0.271 of full scale; tool lists widths 17 to 21 for the worst events.
- Even over time (per 2 s: 155, 160, 134, 153, 134, 140, 144, 140, 140): nothing grows or decays during the capture.
- Start position inside the 256-sample block is spread over all eight eighths (165, 152, 217, 183, 182, 173, 162, 148): not tied to block edges.
- Tool: 0 late blocks, 0 status flags, 0 ADC-time gaps; callback 0.094 to 0.452 ms (mean 0.118).

### 4.3 Other numbers
- Tone frequency 1000 Hz within a few hundredths of a Hz in every mode: no sample-rate mismatch.
- excl128 and shared256 tool verdict "electrical" (50 Hz at -87 dBFS): ignore (D-5).
- S1 (silence): only MME opened; not usable (webcam probably the input; start-up thump; false clicks in digital silence). Details in report v1 section 5.1.

---------------------------------------------------------------------------
## 5. What the app log adds
1. Device inventory by file: webcam microphone 16000 Hz only on WASAPI, Line In 48000 Hz. This fits the S1 "Invalid sample rate -9997" failure if the webcam was the input at 48000 Hz, but S1 itself is not in this log: likely, not proven.
2. ASIO4ALL is in the device list. Earlier in the analysis we said it could not be tested; that applied only to the matrix tool, which has no ASIO key (Correction, section 8).
3. The "block(s) took longer than the block time" warnings appear 5 to 6 s after each capture stopped, when ANALYZE ran in a background thread with the engine still mounted. During the captures the tool saw 0 late blocks. So analysis disturbs audio (D-8); it is not the cause of the bursts.
4. Mount timing may matter (low confidence, 3 data points): the clean exclusive capture was taken 2 min 13 s after its mount; the bad one 7 s after a fresh mount; in session 1 each run was a fresh engine and both exclusive runs were bad.

---------------------------------------------------------------------------
## 6. Hardware or software?

Supported: the engine's output buffer is clean; the damage is in the exclusive-mode input recording; it is not block-locked; no timing problems; the same program and cable are clean in shared mode. Therefore the fault is not in the program's tone generation or mixing. It sits in the exclusive path after the engine: playback driver or card, the analog loop, or exclusive-mode capture. The data cannot say which of the three.
Not excluded: a fault in PortAudio's own exclusive-mode format conversion (the output is captured in the callback before PortAudio converts it). It is not visible in the program's code and cannot be separated with these files.
Not supported by any capture: a bug in `audio_engine.py` mixing, the T023 effect-tail finding (effects were off), hum or broadband noise (-87 to -89 dBFS).

---------------------------------------------------------------------------
## 7. Findings
See `03_findings_register.csv` (F-01 to F-20) and `05_CRACKLE_FINDINGS_final.md`.

---------------------------------------------------------------------------
## 8. Corrections to earlier statements (kept, not silently rewritten)
From report v1 section 7 (still valid): 6 configurations per `--quick` scenario; the webcam suspicion rests on the default-device screenshot and now also on the device list; "formats did not match" was never verified; "tone cut to zero" was a start-up artefact; tool verdict texts are not conclusions.
New in v2:
1. v1 said input and output could not be separated yet: they now are (output.wav), see section 6.
2. v1 said the fault shows at blocks 128 and 256: true for session 1; in session 2 exclusive 128 was clean.
3. "ASIO4ALL cannot be tested" (said in this chat and in the first CRACKLE_FINDINGS) is too broad: the app lists it; only the matrix tool lacks it.
4. The tool report for excl256 says "nothing playing" (D-3) and judges raw.wav without looking at output.wav.
5. The owner's message said matrix results were attached; no matrix summary for the exclusive range test was in the attachments. It is treated as not tested.

---------------------------------------------------------------------------
## 9. Defects in the tools and the program
| ID | Defect | Effect |
|---|---|---|
| D-1 | Click detector counts 1 to 2 step events in digital silence | false clicks, false "high" verdict (S1) |
| D-2 | Verdict per capture, no cross-mode or raw-vs-output comparison | misleading verdicts |
| D-3 | "Nothing playing" text on tone captures | misleading text |
| D-4 | No device names, Windows formats or output capture in matrix meta | cannot prove which device was used |
| D-5 | Hum verdict at -87 to -89 dBFS; "noise floor not meaningful" note on tone captures; duplicate "Input:" line | noise |
| D-6 | `clicks_per_min` counts each event of one burst | inflated count |
| D-7 | 233 ADC-time gaps in WASAPI shared 128, 2 at 256, 0 in exclusive 256 | meaning unclear |
| D-8 | ANALYZE runs while the engine is mounted: late blocks and audio disturbance | confusing warnings |
| D-9 | Legend warning when a capture has no events (`crackle_report.py` 463) | cosmetic |
| D-10 | Ctrl+C logged as CRIT with empty message (`main.py` line 19) | cosmetic |
| G-1 | Mouse-wheel handler crash `'str' object has no attribute 'winfo_containing'` (twice, 14:40:26) | fixed in project v036 (T029), real-PC check open |

---------------------------------------------------------------------------
## 10. Still unknown
1. Which part of the exclusive path creates the bursts (playback, capture, analog loop, PortAudio conversion).
2. Whether any exclusive block size or rate is reliably clean (blocks 64, 512 and 44100 Hz untested); whether the state is decided at stream open.
3. How the latency of each mode actually measures on this PC (not measured by us).
4. ASIO4ALL, WDM-KS, DirectSound behaviour; any other audio device.
5. Whether the owner hears the crackle in the program; Windows volume; Realtek driver version.
6. Silent-input behaviour of the Realtek Line In (S1, S2, S4, S5 not run on Line In).

## 11. Limits
One PC, one cable, one run per cell in most cells; no listening, numbers only; the tool's thresholds were tuned on synthetic signals; recordings are mono channel 0; `output.wav` is taken in the engine callback, not at the speaker.

## 12. Files
See `00_READ_ME_FIRST.md`.
