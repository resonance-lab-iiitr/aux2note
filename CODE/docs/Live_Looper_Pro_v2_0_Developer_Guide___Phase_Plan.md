# Live Looper Pro v2.0: Developer Guide & Phase Plan

*Prepared 2026-11-06. Base: `live_looper_pro.zip` v1.1 (about 2,500 lines of Python) and `latency_lab.py` (539 lines). Target: Windows 10, Python 3.10, Realtek onboard audio, beginner user.*

## 1. Goal of v2.0

Turn the current looper into a low-latency, stable and **fully visible** tool:

1. Use **WASAPI exclusive mode** inside the app (measured 7.5-10 ms round trip instead of 37 ms).
2. Make recording line up in time (latency compensation), so overdubs are tight.
3. Make the DSP fast enough that all effects can run on several tracks without crackling.
4. Show everything in the GUI: mode, real latency, CPU load, dropouts, calibration, debug log.
5. Have automatic tests for every phase, and a debug report the user can paste to Claude.

## 2. What I found in the code (review of v1.1)

| # | Where | Finding | Impact | Fixed in |
| --- | --- | --- | --- | --- |
| 1 | `audio_engine.open_stream` | Opens `sd.Stream` with no `extra_settings`, no `latency` argument, shared mode only. | About 37 ms round trip. | Phase 1 |
| 2 | `app.py` `AudioEngine(... block_size=256)` | Fixed at 256, hard-coded, 48000 Hz hard-coded. | Not configurable. | Phase 1, 4 |
| 3 | `audio_engine.latency_ms` | Adds `stream.latency` values. Measured: wrong by +8 ms (WASAPI shared), -20 ms (WDM-KS), +15 ms (exclusive). | GUI shows a wrong number. | Phase 5 |
| 4 | `_callback` | Holds `self.lock` (RLock) for the whole block, including all DSP. UI actions (add track, arm, save, load) take the same lock. | UI action can stall the audio thread, causing a click. | Phase 2 |
| 5 | `track.feed_recording` / `stop_recording` | Allocates memory each block, then one big `np.concatenate` at stop, run while the lock is held. | Glitch when recording stops on long takes. | Phase 2 |
| 6 | `start_recording_armed` | New take is anchored at the playhead with **no latency compensation**. | Overdubs land late by one round trip. | Phase 2, 5 |
| 7 | `effects.py` `Delay`, `Reverb`, `Compressor` | Per-sample Python loops. Benchmark: reverb 62%, delay 15%, compressor 10-18%, all on about 87% of block time per chain. | Crackling with 2+ chains. | Phase 3 |
| 8 | `effects.py` `Reverb.from_dict` / `set_room_size` | Calls `_build()`, which wipes the reverb tail and allocates buffers (called from the UI thread while audio runs). | Click when moving the room-size slider. | Phase 3 |
| 9 | `_callback` | Effects run only when `np.any(samples)`. A silent block skips the chain, so delay and reverb tails are cut off. | Tails stop abruptly. | Phase 3 |
| 10 | Master bus | Two full `EffectsChain` objects (L and R), so master cost is doubled. | Extra CPU. | Phase 3 |
| 11 | `_callback` | No timing measurement, no xrun counter shown in the GUI (only a log line). | No way to see overload. | Phase 4 |
| 12 | `project_io` | Project file stores no audio settings (driver, block size, calibration). | Settings lost on reload. | Phase 4, 5 |
| 13 | `latency_lab.py` `cmd_dsp_bench` | Prints `%%` instead of `%`. | Cosmetic. | Phase 7 |
| 14 | `main.py` | Sets `SD_ENABLE_ASIO=1`, but there is no ASIO device on this PC. | Harmless. Keep. | - |

What is already good (do not break): the track model, the project zip format, the offline `render_mix`, the log queue (thread-safe), the frozen track header, the keyboard shortcuts.

## 3. Target architecture

```
main.py
app.py                  (GUI shell, only calls engine API; no audio logic)
  audio_settings_panel.py   NEW  driver / mode / rate / block selection
  diagnostics_panel.py      NEW  live latency, CPU, xruns, graph, debug log view
audio_engine.py         (stream + callback + transport)
  stream_config.py          NEW  StreamConfig dataclass, open with fallback ladder
  telemetry.py              NEW  lock-free counters: callback time, xruns, peaks
effects.py              (vectorized DSP)
latency_core.py         NEW  measurement code moved out of latency_lab.py, shared by GUI + CLI
debug_log.py            NEW  ring buffer, log file, debug report export
settings_store.py       NEW  settings.json (last devices, mode, block, calibration)
tests/                  NEW  pytest, no hardware needed
latency_lab.py          (thin CLI that imports latency_core)
```

Rules for every phase:

- The audio callback must **never** block on the UI, allocate big arrays, write files, or log more than once per second.
- The GUI reads engine state only through plain attributes or the telemetry object.
- Every new feature has (a) a pytest test, (b) a visible GUI element or log line, (c) a CHANGELOG line.

## 4. Phase map and token estimates

Free Claude sessions have limited room, so each phase is sized to fit **about 25-40k tokens in total** (reading the files, writing the code, test output, final reply). Estimates are rough; the project files themselves are about 34k tokens if you paste all of them, so **never paste the whole project into one session**. Each phase lists only the files it needs.

| Phase | Title | Files to upload | Est. tokens (in + out) | Risk |
| --- | --- | --- | --- | --- |
| 0 | Baseline, test harness, safety net | audio\_engine, track, effects, project\_io | 25k | Low |
| 1 | Exclusive-mode engine + fallback ladder | audio\_engine, latency\_lab (function `run_one` only) | 30k | Medium |
| 2 | Callback safety + recording compensation | audio\_engine, track | 30k | Medium |
| 3 | DSP vectorization | effects, tests/ | 35k | High |
| 4 | Telemetry + audio settings panel in GUI | audio\_engine, app (selected parts) | 40k | Medium |
| 5 | In-app latency calibration | latency\_core (new), audio\_engine, app (selected parts) | 35k | Medium |
| 6 | Debug center and logging | app (log parts), debug\_log (new) | 30k | Low |
| 7 | Final QA, packaging, docs, v2.0 | everything, but summaries only | 30k | Low |

Total: about 255k tokens across 8 sessions. If a session runs out of room, stop at the last green test, write the handoff note (section 6), and continue in a fresh session. Do not try to squeeze two phases into one.

**Order matters:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Phases 3 and 6 can swap if you want effects sooner. Phase 5 needs Phase 1 and 4.

## 5. Phase details

### Phase 0: Baseline, test harness, safety net (about 25k tokens)

**Purpose:** make a regression net before any change, so later phases can prove they broke nothing.

**Do:**

1. Create `tests/` with `conftest.py` and pytest. Add `requirements-dev.txt` (pytest).
2. Add `tests/fake_stream.py`: calls `engine._callback(indata, outdata, frames, None, status)` in a loop with synthetic input, no sound card.
3. Write baseline tests:
   - add track, record 1 s from a sine, stop, buffer length is about 48000.
   - play back: output equals input times gain and pan.
   - solo, mute, loop region wrap-around.
   - save then load a project: audio and meta identical.
   - `render_mix` equals live callback output for a simple project (EQ only).
4. Add `tools/golden.py`: renders a fixed project and saves `tests/golden/*.npy` (used later to check DSP changes).
5. Add `python -m pytest -q` instructions to README.

**Done when:** `pytest` is green on the unchanged v1.1 code.

**GUI visible:** none (this is the safety net).

### Phase 1: Exclusive-mode engine with fallback ladder (about 30k tokens)

**Purpose:** use the 7.5-10 ms mode inside the app.

**Do:**

1. New `stream_config.py` with `StreamConfig(api, exclusive, sample_rate, block_size, latency, in_device, out_device, channels_in, channels_out)`.
2. In `AudioEngine.open_stream(cfg)`: pass `extra_settings=(sd.WasapiSettings(exclusive=True), sd.WasapiSettings(exclusive=True))` when exclusive, plus `latency="low"`. **Copy the exact argument set that worked in `latency_lab.py` `run_one`** (it already proved 48000 Hz / block 32-128 / mono in, stereo out works on this PC).
3. Fallback ladder, each step logged with a reason: exclusive at the chosen rate → exclusive at the other rate (44100/48000) → shared mode at 48000 → fail with a clear message. If the engine rate changes, tell `Track` and `EffectsChain` (they cache `sample_rate`); simplest rule: **engine rate is chosen before any track exists, otherwise ask the user to start a new project**.
4. Exclusive needs input and output on the same host API (both WASAPI). Validate before opening and explain in the log if not.
5. Defaults for this user: WASAPI exclusive, 48000 Hz, block 64.
6. Keep `sample_rate` and `block_size` constructor arguments, so old tests still work.
7. New tests with a mocked `sounddevice` that raises `PortAudioError(-9997)` for the first N attempts, and checks the ladder order and the final state.

**Done when:** mocked-ladder tests pass; on the real PC, MOUNT shows `WASAPI EXCLUSIVE 48000 Hz / 64` in the log and sound goes out of the Speakers.

**GUI visible:** log lines `[AUDIO] Trying exclusive 48000/64 ... OK` and the status bar shows the mode name. (Full panel comes in Phase 4.)

### Phase 2: Callback safety and recording compensation (about 30k tokens)

**Purpose:** no clicks from the UI, tight overdubs.

**Do:**

1. **Shrink the lock.** The callback takes the lock only to copy a reference to an immutable *snapshot* (`self._tracks_view`, a tuple). UI code builds a new tuple and swaps the reference (atomic in Python). Remove the long lock hold from `_callback`.
2. **Pre-allocate the recording buffer.** `Track` gets a `numpy` array of N minutes (default 5) allocated on arm, a write index, and growth by doubling off the audio thread. `stop_recording` just trims the view, with no `concatenate`.
3. **Pre-allocate callback scratch arrays** (`mix_l`, `mix_r`, `input_signal`) once per stream (sized to `block_size`; reallocate only if `frames` differs).
4. **Latency compensation:** add `engine.record_latency_samples` (default 0). On record start, `track.offset = playhead - record_latency_samples` (clamp at 0, trim the head of the buffer if negative). This value is filled by Phase 5 from calibration; until then the user can type it in the Phase 4 panel.
5. Keep tails alive: run a track's chain while its tail is still ringing (track `tail_samples_left`, set from delay time and reverb room size), even if the input is silent.
6. Tests: stress test that calls UI methods (`add_track`, `arm_track`, `save_project`) from a second thread while the fake callback runs 10,000 blocks, with no exception and the callback maximum time under a limit. Test that a take recorded with a known delay is aligned after compensation.

**Done when:** all Phase 0 tests plus the new ones pass.

**GUI visible:** none yet, but log line `[LOOPER] Record offset compensated by 8.2 ms`.

### Phase 3: DSP vectorization (about 35k tokens, the heaviest)

**Purpose:** all effects on, several tracks, under about 20% CPU per chain.

**Do (use `tests/golden` from Phase 0 to compare):**

1. **Delay:** the delay time (about 350 ms = 16,800 samples) is much larger than the block (64-512), so a whole block can be read and written with slices on the circular buffer (two slices when it wraps). No per-sample loop. Fall back to chunked processing only if `delay_samples < block`.
2. **Reverb:** every comb and all-pass delay line (smallest about 82 samples at 48 kHz) is longer than a block of 64, so process each line with slice reads and writes. For blocks larger than the shortest line, split the block into chunks no longer than the shortest line. The damping low-pass becomes `scipy.signal.lfilter([d],[1,-(1-d)], x, zi=state)`. Rebuild only when the room size changes, and **crossfade or keep buffers** instead of zeroing them.
3. **Compressor:** compute the envelope per small sub-block (16 samples) with `lfilter` for attack/release smoothing on the rectified signal, then compute gain in dB with vectorized `np.log10` and `np.where`. Document that this is a block-rate envelope (tiny audible difference). Optional: if `numba` is installed use a jitted per-sample version (add as an optional extra, never required).
4. **Master bus:** process L and R through one chain as a 2-row array (stateful filters per row), or keep two chains but skip disabled stages cheaply.
5. **Parameter changes from the UI** must not allocate in the audio thread. Apply changes through a small "pending params" dict that the callback reads at the start of the block.
6. Update `latency_lab.py dsp-bench` to print the new numbers (and fix the `%%` print).
7. Tests: new output vs golden output with tolerance (for example max error below -60 dBFS on delay and reverb), stability test (no NaN or inf with extreme parameters), state continuity test (processing 1 block of 4096 equals 64 blocks of 64).

**Done when:** `dsp-bench` shows ALL effects under about 20% per chain at block 64, and all tests pass. **Fallback if the target is missed:** ship the vectorized delay and reverb, keep the compressor as is, and note the result.

**GUI visible:** FX dialog shows a small "CPU cost" label per effect (estimated from a quick benchmark at open time).

### Phase 4: Telemetry and audio settings panel (about 40k tokens)

**Purpose:** make the engine state visible and configurable.

**Do:**

1. New `telemetry.py`: the callback records `time.perf_counter()` start/end, keeps last, average, maximum callback time, a 100-point history array, xrun count, and `status` flags (input underflow, output underflow). All plain numbers, so the GUI can read them without a lock.
2. Engine computes `cpu_load = avg callback time / (frames / sample_rate)` and also reads `stream.cpu_load` from PortAudio. Show both.
3. New `audio_settings_panel.py`, replacing the combo area in panel \[1\]:
   - Driver (WASAPI, WDM-KS, MME, DirectSound, ASIO if present).
   - Mode: **Exclusive / Shared** toggle.
   - Sample rate (44100 / 48000), block size (32 / 64 / 128 / 256 / 512).
   - Input and output device lists, filtered by driver.
   - **Record offset (ms)** field (filled by Phase 5).
   - **Auto (recommended)** button that selects WASAPI exclusive 48000 / 64.
   - Changing a setting while mounted asks to remount.
4. Status bar line: `WASAPI EXCL 48000/64 | RTT 8.2 ms (measured) | CPU 12% | xruns 0 | peak 0.42`.
5. New small **load graph** (Canvas): callback time per block as bars with a red line at the block time. Turns red when above 70%.
6. `settings_store.py`: save and load `settings.json` (last driver, devices, mode, rate, block, record offset). On start, preselect them.
7. Project file adds an `audio` section (rate, block) with defaults for old files.
8. Tests: telemetry math with the fake stream, settings round trip, GUI smoke test (create `Tk`, build panel, change values, destroy).

**Done when:** the user can pick settings in the GUI, mount, and see live CPU and xruns update.

**GUI visible:** audio settings panel, status line, load graph.

### Phase 5: In-app latency calibration (about 35k tokens)

**Purpose:** show the real latency and fix alignment automatically.

**Do:**

1. Move the measurement code from `latency_lab.py` (functions `make_chirp`, `build_signal`, `analyze`) into `latency_core.py`; `latency_lab.py` imports it, so there is one copy.
2. Add `engine.run_calibration()`: while mounted, play a chirp burst train on the output and record the input at the same time (the cable must be connected green to blue), run `analyze`, and return RTT, jitter and level.
3. GUI button **CALIBRATE LATENCY** in the settings panel:
   - Pre-check dialog: "Connect cable from Line Out to Line In, then press Start."
   - Result card: RTT in ms, jitter, signal level in dBFS, status (OK, too quiet, clipping, no signal).
   - If level is clipping, tell the user to lower the Windows playback volume, as in the earlier `--level 0.1` test.
   - On success store the value in `settings.json` and set `engine.record_latency_samples`.
4. Replace `latency_ms()` in the status line: show **measured RTT** when calibrated, otherwise `reported (not measured)` in grey.
5. Optional: a **Latency Test** tab that repeats calibration for each block size and prints a small table like the CLI report.
6. Tests: calibration against the fake stream with a known artificial delay (for example 400 samples) returns that delay within 1 sample; handling of no signal and clipping.

**Done when:** on the real PC, calibration reports a value within about 1 ms of the CLI result, and a recorded overdub lines up with the original beat when checked by the waveform.

**GUI visible:** calibration button, result card, corrected status line.

### Phase 6: Debug center and logging (about 30k tokens)

**Purpose:** when something fails, the user can copy one report and paste it to Claude.

**Do:**

1. `debug_log.py`: log levels (DEBUG, INFO, WARN, ERROR, CRIT), in-memory ring buffer (last 2,000 lines), rotating file `logs/looper.log`, and a `log_rt()` function for the callback that only counts events (the GUI thread turns the counts into lines, so the callback never formats text).
2. Convert the diagnostic panel \[4\] into a tabbed **DEBUG CENTER**:
   - **Log** tab with level filter and search box.
   - **Engine** tab: live values (state, driver, mode, rate, block, RTT, CPU, xruns, queue sizes, track count, playhead).
   - **Devices** tab: the device inventory (current boot scan) plus a **Rescan** button.
   - **Tracks** tab: per track, buffer length, offset, effects on/off, estimated CPU.
3. Button **COPY DEBUG REPORT**: puts into the clipboard a text block with versions (OS, Python, library versions), the settings, the last 100 log lines, the telemetry summary, and the last calibration. Same text saved to `logs/report_<time>.txt`.
4. Global exception handler (`sys.excepthook` and `root.report_callback_exception`) writes the traceback to the log and shows a short, non-scary message.
5. Test mode switch (menu or key **F12**): shows a test signal generator (sine / noise to output) so the user can check sound without a cable.
6. Tests: ring buffer limits, report contains required sections, exception handler logs instead of crashing.

**Done when:** forcing an error (for example mount a wrong device) produces a clear log line and a copyable report.

**GUI visible:** the whole Debug Center and the copy button.

### Phase 7: Final QA, packaging, docs, release v2.0 (about 30k tokens)

**Do:**

1. Run the full test suite, then the manual checklist (section 7) on the real PC and record results in `docs/QA_RESULTS.md`.
2. Soak test: record, overdub 4 tracks, all effects on, 10 minutes, xruns must be 0 at block 64 (or document the safe block size).
3. Optional packaging: `pyinstaller --onedir main.py` and a `run_looper.bat` that checks Python and installs `requirements.txt`.
4. Update `README.md` (setup, exclusive mode note, troubleshooting table from the handoff) and `CHANGELOG.md` (v2.0 entry).
5. Fix `latency_lab.py` `%%` print if not already done; add `latency_lab.py` to the zip.
6. Version bump to 2.0 in the window title and the project file.

**Done when:** the QA checklist is all green and a release zip is produced.

## 6. How to run a phase in a fresh Claude session

### Start-of-session message (copy this)

> I am continuing the Live Looper Pro v2.0 plan. This session is **Phase N**. I attach: (list files from the phase table) and the Developer Guide. Read only the "Phase N" section and sections 1-3. Do only that phase. Beginner user on Windows 10, Python 3.10, give step-by-step commands. Show the exact files you changed, run the tests you can, and tell me what to run on my PC and what I should see in the GUI.

### Rules for each session

1. Upload only the files named in the phase table plus the latest `HANDOFF_phaseN.md`.
2. Claude must run `pytest` (where a sandbox is available) before and after the change.
3. Return **full replacement files** for small files, and clear before/after edits for large ones (`app.py`).
4. At the end, Claude writes a handoff note (below). The user saves it and uploads it in the next phase.
5. If the session is running out of room: stop after the last green test, do not start a new sub-task, write the handoff.

### End-of-session handoff template

```
# HANDOFF after Phase N
Status: DONE / PARTIAL (what is missing)
Files changed: (list, with line counts)
New files: (list)
Tests: X passed / Y total, command used
GUI checks the user must do on the PC: (steps and expected result)
Known issues: (list)
Decisions made: (list, e.g. engine rate fixed per project)
Next phase needs: (files to upload)
Tokens used: about K
```

### If a phase is too big for one session

Split it like this (already planned):

- Phase 3: 3a = Delay + Reverb, 3b = Compressor + master bus + tests.
- Phase 4: 4a = telemetry + status line, 4b = settings panel + settings.json.
- Phase 6: 6a = debug\_log + report, 6b = tabs + test signal.

## 7. Test and QA plan

### 7.1 Automated (no hardware, run with `python -m pytest -q`)

| Area | Tests | Phase |
| --- | --- | --- |
| Engine transport | record, play, loop wrap, solo, mute, pan, gain | 0 |
| Project IO | save/load round trip, old-version file loads | 0, 4 |
| Stream open | fallback ladder with mocked PortAudio errors | 1 |
| Threading | UI calls during callback, callback max time | 2 |
| Alignment | take recorded with known delay, compensation | 2, 5 |
| DSP | golden comparison, block-size independence, NaN safety | 3 |
| Telemetry | CPU % math, xrun counter | 4 |
| Settings | `settings.json` round trip, bad file ignored | 4 |
| Calibration | known delay found within 1 sample, no signal, clipping | 5 |
| Debug | ring buffer, report sections, exception hook | 6 |
| GUI smoke | build window, press buttons through `invoke()`, destroy | 4, 6 |

### 7.2 Manual on the real PC (what the user checks)

| Step | What you do | What you should see |
| --- | --- | --- |
| M1 | `python main.py` | Window opens, Debug Center shows the device inventory, no error lines. |
| M2 | Press AUTO, then MOUNT | Status: `WASAPI EXCL 48000/64`. Log: exclusive OK. |
| M3 | Enable input monitor, play or speak | You hear yourself with almost no delay. Input meter moves. |
| M4 | Run CALIBRATE LATENCY with the cable | RTT about 8 ms, level OK, record offset set. |
| M5 | Record a loop, overdub a second track | The two tracks line up. No gap or flam at the start. |
| M6 | Turn on all effects on 4 tracks | CPU graph stays green, xruns 0. |
| M7 | Drag the reverb size slider while playing | No click, no tail cut. |
| M8 | Save project, close, open, load | Same audio, same effects, same audio settings. |
| M9 | Export mix (WAV and MP3) | File plays and matches what you heard. |
| M10 | Start another sound app while mounted | Clear message in the log (exclusive device busy), app does not crash. |
| M11 | COPY DEBUG REPORT | Clipboard text has versions, settings, last 100 log lines. |

### 7.3 Pass criteria for v2.0

- Measured RTT at most 12 ms in exclusive mode at block 64.
- 0 xruns in the 10-minute soak test with all effects on 4 tracks (or a documented safe block size).
- All automated tests green. Every phase has a CHANGELOG entry.

## 8. What the user sees in the GUI (summary)

| Element | Location | Introduced |
| --- | --- | --- |
| Mode name in status line | top status | Phase 1 |
| Audio settings panel (driver, mode, rate, block, AUTO) | panel \[1\] | Phase 4 |
| Live CPU %, xruns, measured RTT | status line | Phase 4, 5 |
| Load graph | beside meters | Phase 4 |
| CALIBRATE LATENCY button and result card | panel \[1\] | Phase 5 |
| Record offset field | panel \[1\] | Phase 4, 5 |
| FX "CPU cost" labels | FX dialog | Phase 3 |
| Debug Center tabs (Log, Engine, Devices, Tracks) | panel \[4\] | Phase 6 |
| COPY DEBUG REPORT, test signal (F12) | Debug Center | Phase 6 |

## 9. Risks and answers

| Risk | Mitigation |
| --- | --- |
| Exclusive mode blocks other apps. | Show a warning badge when exclusive is on; fallback ladder to shared. |
| Changing sample rate with tracks loaded. | Rate fixed per project; require a new project to change it. |
| Vectorized reverb sounds slightly different. | Golden tests with tolerance; keep the old class as `ReverbReference` for the tests. |
| Python callback too slow at block 32. | Default to block 64; show the safe-block recommendation from the soak test. |
| Session runs out of tokens mid-phase. | Sub-phase splits in section 6, and a handoff note at the last green test. |
| User's PC has no cable. | Calibration is optional; manual record offset field and a test tone remain. |

## 10. Backlog (after v2.0, not in the plan)

Undo/redo, MIDI footswitch for record and play, per-track input channel choice, stereo recording, time-stretch, VST hosting, count-in and metronome, ASIO via FlexASIO.

## 11. Decisions I assumed (change them before Phase 1 if you disagree)

1. Default mode is WASAPI exclusive, 48000 Hz, block 64, with automatic fallback to shared mode.
2. Mono input, stereo output stays as is.
3. The user wants to hear themselves live, so latency work comes before effects work.
4. All eight phases are included (you said to select all).
