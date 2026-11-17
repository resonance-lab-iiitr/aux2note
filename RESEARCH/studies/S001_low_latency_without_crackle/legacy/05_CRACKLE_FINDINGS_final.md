# Crackle findings (T024 final, 2026-11-12)

Sources: `DELIVERABLES/T024_findings/01_REPORT.md` (first session: S1, S3 quick matrix), the three Lab-tab captures of 14:42 to 14:45 (`DELIVERABLES/T024_findings/lab_captures_2026-11-12/*/report.md`), and `analysis/analysis_output_lab_captures.txt` (independent re-analysis of raw.wav and output.wav, script `analysis/analyze_lab_captures.py`). Real PC: Windows 10, Realtek onboard, one 3.5 mm cable green (line out) to blue (line in), Line In default, formats 24 bit / 48000 Hz. Judged from numbers only; nobody listened to the files. Tool verdict texts are hypotheses (defects D-1..D-7 in the report, section 8).

## Short answer
1. In WASAPI exclusive mode the recorded input gets dense short noise bursts; shared WASAPI and MME stay clean. It is **not** the program's own tone or mixing: `output.wav` (the block the engine hands to the sound API) is a perfect sine in all three Lab captures, including the one whose `raw.wav` is damaged.
2. So the fault enters **after the engine's output buffer**: exclusive-mode playback driver or card, the analog loop, or exclusive-mode capture. The data cannot say which of these three; "hardware or driver, in the exclusive path" is the supported statement. A bug in the program's engine, tone or mixer is not supported by any capture.
3. The fault is **intermittent**: exclusive 128 was bad on the first session (143 bursts/s) and clean on the second (0 bursts). Exclusive 256 was bad both times.
4. Practical answer for this PC: use **WASAPI shared (or MME)**. Exclusive mode is not trustworthy here until a driver / Windows variable is changed and re-tested.

## S3 tone loopback (all rows: 48000 Hz, 20 s, effects and monitoring off)
Burst count: "my fit" = bad samples (residual > 0.02 against a fitted 1 kHz sine) joined into bursts; "tool" = clicks counted by crackle_report. Tone error = rms of the residual against the fit, relative to the tone.

| Session | Mode | Block | raw.wav tone error | Bursts per s (my fit) | Tool clicks per min | output.wav | Late blocks / status flags | Tool verdict (read with care) |
|---|---|---|---|---|---|---|---|---|
| 1 (matrix) | MME | 128 | -62.7 dB | 0 | 2.99 | not captured | 0 / 0 | electrical, hum -89 dBFS: ignore |
| 1 (matrix) | MME | 256 | -62.5 dB | 0 | 2.99 | not captured | 0 / 0 | same |
| 1 (matrix) | WASAPI shared | 128 | -62.4 dB | 0 | 8.96 | not captured | 0 / 0 | hardware_or_driver_input (only tone-onset events) |
| 1 (matrix) | WASAPI shared | 256 | -61.7 dB | 0 | 8.97 | not captured | 0 / 0 | same |
| 1 (matrix) | WASAPI exclusive | 128 | -8.8 dB | 143 | 8796 | not captured | 0 / 0 | hardware_or_driver_input (medium) |
| 1 (matrix) | WASAPI exclusive | 256 | -5.2 dB | 87 | 5278 | not captured | 0 / 0 | hardware_or_driver_input (high) |
| **2 (Lab) excl128** | WASAPI exclusive | 128 | **-60.7 dB** | **0** | 0.0 | **clean (-152.5 dB)** | 0 / 0 | electrical (hum -87.4 dBFS: ignore) |
| **2 (Lab) excl256** | WASAPI exclusive | 256 | **-10.2 dB** | **72.7** (1382 bursts, median gap 9.0 ms, median width 19 samples, largest residual 0.271) | **6009** (2003 clicks) | **clean (-152.5 dB)** | 0 / 0 | hardware_or_driver_input (high) |
| **2 (Lab) shared256** | WASAPI shared | 256 | **-61.5 dB** | **0** | 3.0 (1 event at 41.8 ms, tone onset) | **clean (-152.5 dB)** | 0 / 0 | electrical (hum -87.5 dBFS: ignore) |

(session 1 bursts per s: values from the first report; session 2 values from `analysis_output_lab_captures.txt` and each report.md. The two counting methods differ a little, so compare modes, not decimals.)

Other scenarios: S1 silence (only MME opened, device probably the webcam: not usable), S2, S4, S5, 44100 Hz, blocks 64 and 512, DirectSound, WDM-KS, ASIO / ASIO4ALL: **not tested**. The exclusive range matrix (`--scenarios S3 --apis wasapi-excl --rates 44100,48000 --blocks 64,128,256,512`) was announced but no matrix_summary was attached: **not tested**. The code has no ASIO entry (API_KEYS in tools/crackle_matrix.py lists wasapi-excl, wasapi-shared, mme, directsound, wdmks; nothing about ASIO in audio_settings_panel.py or stream_config.py), so ASIO4ALL cannot be tried with the present tools.

## What points to hardware / driver, what to software
Points to the hardware / driver side (after the engine):
- `output.wav` is clean (error -152.5 dB, peak exactly 0.3000, both channels) in the very run whose `raw.wav` has 1382 bursts (excl256).
- The engine saw nothing: 0 late blocks, 0 PortAudio status flags, callback time 0.09 to 0.45 ms per block against a 5.3 ms block at 256 (blocks.csv.gz, `cb_ms`), 0 ADC-time gaps in excl256.
- Bursts are not tied to the block: start position inside the 256-sample block is spread over all eight eighths (165, 152, 217, 183, 182, 173, 162, 148); they come about every 9 ms, evenly over the 20 s (155, 160, 134, 153, 134, 140, 144, 140, 140 per 2 s). A callback or buffer-edge bug would line up with block edges.
- Same program, same cable, same block size: shared256 is clean, exclusive256 is not. The mode changes the result, not the program's signal.
- Intermittent: excl128 clean in session 2, bad in session 1.
- Size: bursts of 17 to 21 samples (about 0.4 ms) with residuals up to 0.27, no dropouts and no clipping reported.

Points to software (the program):
- None seen in these captures. The engine's output is an exact tone. Open: the program opens 1 input channel for the stereo Line In (F-08); it does not explain bursts that appear only in one mode.
- Limit of the evidence: `output.wav` is taken in the engine callback (`cap.feed(indata, outdata, ...)` in audio_engine.py) before PortAudio converts and hands the data to the exclusive driver. A fault in PortAudio's own exclusive-mode conversion is not excluded; it is also not a program-code fault we can see.

## Best driver and block size on this PC (supported by the data)
WASAPI shared, 256 (clean in session 1 and session 2) or 128 (clean in session 1); MME 128 / 256 (clean, but the tone arrives about 0.23 s later at start-up, report 5.2). WASAPI exclusive: 3 of 4 runs bad (128 bad then clean, 256 bad twice): not recommended. Latency was not measured.

## Ranked fixes
1. Run the app in WASAPI shared mode on this PC (setting only). Evidence: 5 of 5 shared / MME captures clean.
2. Re-test exclusive after one Windows change at a time with the Lab test tone at block 256 (the size that failed twice): untick "Give exclusive mode applications priority"; Realtek enhancements off; Microsoft "High Definition Audio Device" driver instead of Realtek's; note the Realtek driver version. Not done yet.
3. Repeat the exclusive range (blocks 64 / 128 / 256 / 512, 44100 and 48000 Hz) with `--apis wasapi-excl` to see if any size is reliably clean (the 128 result shows one run is not enough: repeat each 3 times).
4. Try another output / input device (USB headset or interface) in exclusive mode to see if the fault is specific to the Realtek.
5. Fix the Crackle Lab tool defects D-1, D-3, D-4 (device names in meta; false clicks in digital silence; wrong "nothing playing" text) before trusting more verdicts. New in this session: the Lab verdict "hardware_or_driver_input" for excl256 says "nothing playing" although a tone was played (D-3 again), and it says "clicks present in the raw capture" while it has not looked at output.wav (cross-check of raw vs output is not in the tool: add to D-2).
6. Software items that stay on the list but are not shown by data: F-08 (1 input channel for a stereo input), T023 effect-tail finding.

## Does the T023 finding (effect tail cut at exact-silence blocks) show up in a real capture?
Not observable. All real captures so far were tone loopbacks with effects off and no clips; the cut needs a track clip that ends in exact digital silence with a delay / reverb tail. Status stays "synthetic only" (tests/test_phase10_baseline.py). It needs a real project render to check; it does not explain the bursts (effects were off).

## Cleanup method for T025 to build first
A **short-burst declicker for the recorded track**: detect 15 to 50 sample impulsive bursts (here width 17 to 21 samples, residual up to 0.27, about 70 per second, not tied to block edges) and repair them by interpolation across the burst (for example autoregressive interpolation from the clean samples on both sides). Reason: the damage seen is exactly this kind, and it is independent of the signal. Caveats: the burst rate here (about 1 every 9 ms) is far above normal click repair; the declicker must not be the "fix" for exclusive mode (use shared mode first), and music with dense transients may need a conservative threshold. Hum / broadband noise reduction is not supported by any capture (the "hum" verdicts are at -87 to -89 dBFS).

## Open items
- Owner notes asked for in the handoff (jack colours, Windows volume, Realtek driver version, what was heard in the program) were not supplied; the jack colours are as the owner stated.
- GUI defect found during the tests (scroll_frame.py, mouse wheel): task T029 (audio not affected).

## Update: app log looper.log (14:39 to 14:51, 2026-11-12)
File: `DELIVERABLES/T024_findings/evidence/looper_2026-11-12.log`. It covers the three Lab captures.
- Device inventory confirmed by file (14:39:07): WASAPI ID 12 webcam microphone 16000 Hz only; WASAPI ID 13 Line In 48000 Hz [DEFAULT-IN]; WASAPI ID 11 Speakers 48000 Hz [DEFAULT-OUT]. This supports the owner's explanation of the S1 -9997 failure (webcam as default input), but S1 itself is not in this log, so it stays "likely, not proven".
- Correction: the text above says ASIO4ALL "cannot be tested" because the code has no ASIO entry. Only the matrix tool has no ASIO key. `main.py` line 9 sets `SD_ENABLE_ASIO=1` and the log lists `ID 10 | ASIO | ASIO4ALL v2 [DEFAULT-IN, DEFAULT-OUT]` (2 in / 8 out). So the Lab tab can probably capture through ASIO4ALL if the Audio tab offers that driver (not checked: not seen on screen). Only the matrix tool cannot. Ranked fix 4 (other devices) gains: "Lab tab test tone through ASIO4ALL, block 256, 3 captures".
- Late blocks: the log shows `[AUDIO] n block(s) took longer than the block time` (worst 447 % at 14:42:42-43, 227 % at 14:44:40-43, 113 % at 14:45:59), while every capture's blocks.csv.gz has 0 late blocks. The warnings come 5 to 6 s AFTER each capture stopped (14:42:37, 14:44:35, 14:45:53), when ANALYZE ran in its background thread (tab_lab.py line 572) with the engine still mounted. So the analysis step steals CPU from the audio callback; this did not happen during the captures. It is a Lab usability defect (new D-8: tell the user to UNMOUNT before ANALYZE, or lower the thread priority), not a cause of the bursts.
- Wheel error confirmed: two identical tracebacks at 14:40:26 (Python 3.10, `scroll_frame.py` line 58 in `_pointer_widget`, called from line 68 in `_on_global_wheel`). The owner runs `D:\PROJECT_v032\PROJECT\CODE`. Task T029.
- Mount history (new, a possible factor, not tested): excl128 was captured 2 min 13 s after its mount (14:40:04 to 14:42:17) and was clean; excl256 was captured 7 s after a fresh mount (14:44:08 to 14:44:15) and was bad; in session 1 every run was a fresh engine and both exclusive runs were bad. Inside the bad 20 s capture the bursts are even from start to end (155, 160, 134, 153, 134, 140, 144, 140, 140 per 2 s), so nothing decays within a capture. Hypothesis: the fault is decided when an exclusive stream is opened (it is either there or not for the whole stream). Test: mount and unmount exclusive 256 five times, 10 s capture each, and count bad ones.
- Cosmetic defects: (D-9) matplotlib warning `No artists with labels found to put in legend` at crackle_report.py line 463: `ax.legend(...)` is called even when a capture has no events (the excl128 capture had 0); (D-10) a Ctrl+C in the console at 14:51:35 is logged as `CRIT Unexpected error in main thread` with an empty message (KeyboardInterrupt, main.py line 19); harmless.
- Shared mode log line says expected round trip about 37 ms (14:45:13). Not measured by us.
