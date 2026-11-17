# QA results - Live Looper Pro 2.0

Status: **PARTIAL. Soak and latency measured on the real PC (below). Manual checklist M1-M13 and the GUI rows M19-M28 NOT yet done. Not released.**
Cells that are blank have not been verified. Fill them in, then change the status line.

## 1. Automated tests (sandbox, no sound card)

| Item | Result |
| --- | --- |
| Command | `python -m pytest -q` (also `python -m unittest discover -s tests -t .`) |
| Environment | Linux sandbox, Python 3.12, 1 shared CPU core, no Tk, no sound card |
| Result | 140 passed, 5 skipped, 0 failed |
| Skipped (need a real window) | Tk smoke tests of the settings panel and Debug Center |
| Later sandbox runs | Python 3.12 with Tk under Xvfb: 373 tests OK, 0 skipped (end of T016, 2026-11-11). Older numbers in this table are from earlier releases. Command: `python3.12 -m unittest discover -s tests -t .` |
| On the real PC | `python -m unittest discover -s tests -t .` (rc4): 149 tests OK, 0 skipped. rc5: **156 tests OK, 0 skipped** (2026-11-07; pytest 9.2 crashes on that PC, use unittest) |

## 2. Soak test, offline (CPU headroom, sandbox)

Command: `python tools/soak_test.py --offline --minutes 1 --block N`
Scenario: 4 takes recorded/overdubbed, every effect on 4 tracks and on the master bus.
This sandbox has 1 shared core, so timing spikes are noisy; the numbers show headroom, not the real PC.

| Block | Block time | Avg CPU | Worst callback | Overruns in 1 min |
| --- | --- | --- | --- | --- |
| 64 | 1.33 ms | 44-66 % | 4.5-9.5 ms | 37-107 (3 runs) |
| 128 | 2.67 ms | 26 % | 4.9 ms | 12 |
| 256 | 5.33 ms | 20 % | 6.4 ms | 1 |

Observations:
- `dsp_bench` at block 64: one full chain = 8.1 % (Phase 3 target < 20 %: met).
- 4 tracks + master (two chains) = 6 chains, so about 50 % average at block 64 matches the per-chain figure.
- Worst-callback spikes of 4-10 ms occur at every block size and do not go away with garbage collection off, so they look like sandbox scheduling noise, not DSP cost. This is a guess until it is measured on the real PC.
- The master bus still runs two full chains (one per channel). Phase 3 listed a one-chain option; it was not done. If the real-PC soak fails at block 64, this is the first thing to optimize.

## 3. Soak test, live (REAL PC) - 10 minutes, 4 takes, WASAPI exclusive 48000 Hz

PC: Windows 10 (19041), Python 3.10, Realtek onboard audio. **Power plan: High performance.**
Command: `run_soak.bat <block> 10` (all effects) or `python tools\soak_test.py --live --minutes 10 --block 128 --fx typical`.
`overruns` is the real failure number (`xruns` stays 0 in exclusive mode).

| Block | Effects | Avg CPU | Max callback | Late blocks (overruns) | Verdict |
| --- | --- | --- | --- | --- | --- |
| 64 | all | 55.1 % | 2.51 ms | 9 of 450,018 | FAIL (rare) |
| 128 | all | 32.6 % | 3.21 ms | 6 of 225,025 | FAIL (rare) |
| 128 | all (2nd run) | 31.8 % | 3.19 ms | 7 of 225,006 | FAIL (rare) |
| 128 | typical | 13.6 % | 0.81 ms | **0** of 225,023 | **PASS** |
| 256 | all | 21.1 % | 3.70 ms | **0** of 112,513 | **PASS** |
| 256 | all (2nd run) | 19.6 % | 1.81 ms | **0** of 112,511 | **PASS** |

Typical effects = EQ + compressor on every track, reverb on one track, EQ on the master.

Same code on the **Balanced** power plan (1-minute runs): block 64 typical 395 late blocks, block 128 all effects 843, so the power plan was the main cause of the original failure.
Not measured: block 64 with typical effects for 10 minutes (1-minute run was clean); the exact cause of the rare late blocks (about 3 ms stalls, probably Windows background activity: a guess).

Safe block size for this PC: **128 for typical use, 256 with every effect on every track.**

## 4. Manual checklist on the real PC

Tick when done. Write what you saw if it differs.

| Step | What you do | What you should see | Pass? | Notes |
| --- | --- | --- | --- | --- |
| M1 | `python main.py` (or run_looper.bat) | Window titled "Live Looper Pro 2.0", Debug Center shows the device inventory, no error lines | PASS | rc5, 19 devices listed, no errors |
| M2 | AUTO, then MOUNT | Status `WASAPI EXCL 48000/128`, log `Trying exclusive 48000/128 ... OK` | FAIL on rc5, retest on rc6 | rc5 AUTO picked the webcam microphone (16000 Hz): `Invalid sample rate` in every mode. Fixed in rc6, not yet verified on the PC. |
| M3 | Input loopback on, play or speak | You hear yourself with almost no delay; input meter moves | | |
| M4 | CALIBRATE LATENCY with the cable | RTT about 8 ms, level OK, record offset filled | PASS at 128 | Block 128: RTT 9.60 ms, jitter 0.00, level -8.6 dBFS, 6 of 6 bursts. Block 256: RTT 12.29 ms, level -8.4 dBFS, 6 of 6. Block 64 not measured. |
| M5 | Record a loop, overdub a second track | Tracks line up; no gap or flam at the start | | |
| M6 | All effects on 4 tracks | LOAD graph green, xruns 0 | | |
| M7 | Drag the reverb size slider while playing | No click, tail not cut | | |
| M8 | Save, close, open, load | Same audio, same effects, same audio settings | | |
| M9 | Export WAV and MP3 | Files play and match what you heard | | |
| M10 | Start another sound app while mounted | Clear message in the log (device busy), app does not crash | | |
| M11 | COPY DEBUG REPORT, paste in Notepad | Sections VERSIONS, SETTINGS, ENGINE, TELEMETRY, CALIBRATION, DEVICES, LAST 100 LOG LINES; file in logs\ | | |
| M12 | F12, START Sine (low Windows volume) | Quiet tone from the speakers; STOP ends it | | |
| M13 | Double-click `run_looper.bat` | App opens; if Python is missing, a clear message | | |
| M19 | Start the app, then maximize and press F11 twice | Window fills the screen; F11 toggles full screen and back; all four tabs fit without cut-off | | |
| M20 | Tracks tab: add 3 tracks, `Ctrl+wheel` over a clip, `Shift+wheel`, ZOOM -/+/FIT | Ctrl+wheel zooms about the pointer, Shift+wheel scrolls sideways, ruler follows | | |
| M21 | Tracks tab: record a take and watch the waveform | Waveform grows while recording and is complete after STOP; no freeze | | |
| M22 | Tracks tab: drag a clip, Shift+drag, Alt+drag, Left/Right nudge | Snaps (yellow guide); Shift+drag is 10x slower; Shift or Alt turns snapping off (Alt may be taken by the Windows menu: note it); arrows nudge 10 ms / 100 ms with Shift | | |
| M23 | Mixer tab with real audio playing | Level meters move; ARM / M / S match the Tracks tab both ways; fader and PAN follow | | |
| M24 | Mixer tab: move the master fader, then the top-bar master slider | Both always show the same value | | |
| M25 | Debug tab with a mounted stream | Log level chips and search work; Engine cards update; Load graph moves | | |
| M26 | Audio tab while mounted | Live Status shows mode, round trip, CPU, dropouts and moving meters; "not mounted" after UNMOUNT | | |
| M27 | `Ctrl+plus` x3, `Ctrl+minus`, `Ctrl+0`, then restart the app | Scale steps 10 % each, resets to 100 %, last value restored at start; test the US-layout keys `Ctrl+=` and `Ctrl+Shift+=` | | |
| M28 | UI scale 150 % and 200 % on the real screen | Everything readable; from 130 % the top bar has two lines; note any cut-off | | |
| M29 | Lab tab: Audio tab MOUNT, Lab tab, Silent input 20 s, START CAPTURE | Capture stops by itself; folder `captures\<time>_<label>\` has raw.wav, blocks.csv.gz, meta.json | PARTIAL 2026-11-12 | ran with Test tone (not Silent input) 3 times, 20 s each; folders have raw.wav, output.wav, blocks.csv.gz, meta.json; silent-input case not run |
| M30 | Lab tab: ANALYZE the capture | Verdict, evidence lines and report.png shown; `analysis\analysis_pack.zip` exists | PASS 2026-11-12 | analysis_pack.zip, report.md, report.png, events.csv made for all 3 captures (14:42 to 14:45) |
| M31 | `run_crackle_matrix.bat --dry-run` | Prints the plan and total time; opens no sound device | PASS 2026-11-12 | 16 configurations x 5 scenarios, about 31 min; also --help OK |
| M32 | `run_crackle_matrix.bat --quick` (follow the cable prompts) | Finishes; `matrix_summary.md` and `.csv` written; no run is `run_failed` | PARTIAL 2026-11-12 | quick runs of S1 and S3 only (separate commands); both finished and wrote matrix_summary.md/.csv; WASAPI failed with -9997 in S1, ok in S3; S2, S4, S5 not run |
| M33 | Attach `analysis_pack.zip` and `matrix_summary.md` to a Claude chat | Claude can read the verdict and the table | PASS 2026-11-12 | attached packs and matrix summaries were read (T024) |

## 5. Pass criteria for 2.0

| Criterion | Status |
| --- | --- |
| Measured RTT at most 12 ms, exclusive (M4) | **met at block 128 (9.60 ms)**; block 256 = 12.29 ms (0.29 ms over); block 64 not measured |
| 0 xruns in 10-minute live soak with all effects on 4 tracks, or a documented safe block size (section 3) | **met by documented safe sizes**: 256 for all effects (0 late blocks, twice), 128 for typical effects (0 late blocks). 128 with all effects: 6-7 rare late blocks |
| All automated tests green | **done**: rc5 on the PC 156 OK, 0 skipped; sandbox 156 OK, 5 skipped (Tk) |
| CHANGELOG entry for every phase | done (checked by tests/test_phase7.py) |

Release decision: ______ (date, name) - not before M1-M3, M5-M13 and M19-M33 are ticked
