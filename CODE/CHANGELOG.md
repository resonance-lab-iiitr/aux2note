# Changelog

## v2.0-rc12 - crackle fix: split streams on by default, AUTO block 160
Found with tools/split_test.py on the test PC (WASAPI, Microsoft HD Audio): ONE exclusive duplex stream crackles at every block size (about 1000-2900 clicks/min, status flags 0, so it is not a callback overrun). Separate input and output streams are clean at block 256 and 64, but split with exclusive input at block 128 is BAD (about 4000 clicks/min).
1. **Split in/out is now the default** (`DEFAULT_SETTINGS["split"]`, the panel checkbox and the AUTO button). The old default opened the single duplex stream.
2. **AUTO block is 160** (was 128). One constant: `settings_store.AUTO_BLOCK`. 160 is not yet confirmed by a long split_test.py run on the test PC; change the constant if it is not clean.
3. **Old settings.json is migrated once** (`audio_defaults` = 2): a file without it gets split on and block 128 replaced by 160. Other block sizes are kept; after the migration the user's own choice is kept.
4. AUTO log line now prints the real rate and block size.
- Tests: updated the defaults tests, added LegacySettingsMigrationTests. Latency: split adds about one block (PREFILL_BLOCKS) - re-measure the round trip.

## v2.0-rc11 - tabbed full-screen GUI (phase 9)
The single crowded window is replaced by a top bar plus four tabs. No audio or DSP behaviour changed (golden files untouched).
1. **App shell (T010):** persistent top bar (transport, master volume, meters, status line) and tabs Tracks / Mixer / Audio / Debug; opens maximized, F11 full screen, `Ctrl+1`..`Ctrl+4` switch tabs.
2. **Tracks tab (T011, T015):** full-screen editing workspace with ZOOM -/+/FIT, Ctrl+wheel zoom about the pointer, ROWS -/+, wheel and Shift+wheel scrolling, virtual horizontal scrolling (deep zoom stays fast), follow-playhead only while playing. Clip editing: click to select, drag with snapping (playhead, 0, other clips; Shift or Alt turns snapping off, Shift+drag = 10x slower), Left/Right nudge 10 ms (Shift 100 ms), time readout, double-click opens FX, double-click the name renames.
3. **Mixer tab (T014):** channel strips with live level meters (new per-track `Track.peak`), ARM / M / S, PAN, fader with dB readout, five FX buttons, MASTER strip in step with the top-bar slider.
4. **Audio tab (T012):** devices, calibration, monitoring switches and a big Live Status. **Debug tab (T013):** Log with level chips and search, Engine cards, sortable Devices and Tracks, Load graph, Report preview.
5. **UI scale (T016):** 80-200 %, `Ctrl+plus` / `Ctrl+minus` / `Ctrl+0` and View menu, saved as `ui_scale` in settings.json. From 130 % the top bar wraps onto a second line.
6. **Foundation (T008, T009):** theme and scalable fonts (`ui_theme.py`), `scroll_frame.py`, `timeline_view.py` (zoom, fit, row heights, ruler ticks), screenshot helper `tools/gui_shot.py`.
- README: new window tour, shortcut table, project layout; test command is unittest (pytest crashes on the test PC).
- Tests: 373 at the end of T016 (sandbox, Xvfb, all OK). T017 could NOT re-run them (no Tk in that session); see the session note.
- Known limits: at 200 % on a 1366 px screen the top bar row 1 is wider than the screen (175 % fits); Mixer strips are rebuilt on each scale change (meters reset); VOL and PAN sliders overlap a little in the 96 px track row. Real-PC checks are rows M19 onward in docs/QA_RESULTS.md.

## v2.0-rc10 - clean audio pack (crackle / noise / pops)
Found while testing M3-M7: crackle at the END of notes, constant clicks, and a buzz after STOP.
1. **STOP now really stops.** The callback kept mixing the same frozen block when the transport was stopped (a buzz). Playback now fades out over ~8 ms on STOP, fades in on PLAY, and tracks are skipped while stopped.
2. **CLEAN INPUT** (new checkbox, on by default): a 20 Hz DC blocker plus a gentle downward expander (threshold -55 dBFS, 2:1, max -30 dB, 1 ms attack, 100 ms release) on the live input, before monitoring, recording and all effects. Hiss and the noisy end of a fading note are no longer amplified by the compressor / distortion. The IN meter still shows the raw input.
3. **Distortion**: first-order anti-derivative anti-aliasing (ADAA) instead of plain tanh (27-55 dB less aliasing in tests, no latency apart from a 0.5-sample smoothing), and small-signal gain capped at 6x (was 10x), so quiet tails are boosted less. Sound at the same drive setting is therefore a little less extreme.
4. **Master limiter**: plain tanh (which bent even quiet signals) replaced by a transparent soft-knee limiter: unchanged below 0.8, smoothly rounded above, never over 1.0. Live output and exported mixdown use the same function. Note: normal levels are now a little louder than in rc9.
5. **Smoothing (no zipper clicks)**: master volume, track volume, pan, mute/solo, distortion drive/mix, compressor threshold/ratio/makeup, delay mix, reverb mix and room size now glide over ~8-10 ms; changing the delay TIME crossfades between old and new tap. Not smoothed (known gap): EQ band gains, delay feedback.
6. **Tails and denormals**: a track's chain keeps running at least 0.25 s after its audio ends, the last block is faded, then ALL filter/delay/reverb memory is cleared in place (no stale state to click on the next note). Stopping the transport clears it too. Always-running master chains get a cheap sweep that zeroes values below 1e-30 (1/8 of the work every ~40 ms) so decaying tails never become slow denormal numbers. (Python cannot set the CPU's flush-to-zero flag, hence the sweep.)
- Not done: crossfade at the loop-wrap point and at record punch-in/out.
- Tests: 198 (was 161). Updated on purpose: engine / project tests that expected tanh, the room-size test (now glides), golden `all_fx` (distortion changed; delay / reverb / compressor baselines untouched and still match to 3e-8). New: tests/test_phase8_clean_audio.py. Tests that check bit-exact audio paths run with CLEAN INPUT off (tests/fake_stream.py).
- CPU: about +0.2 ms per block on average in the worst case (4 tracks, every effect, master FX, live monitoring) on the build sandbox; worst block 1.1-1.5 ms against a 2.67 ms budget. Re-run the soak on the real PC.
- Includes the rc7 layout, rc8 ruler and rc9 export-button fixes.

## v2.0-rc9 - EXPORT MIX button stayed on "RENDERING..." (found at checklist M8)
- Bug: the export itself worked (the file was written and "Mixdown exported" was logged within a second), but the button kept saying RENDERING... and stayed greyed out, so a second export was impossible without restarting.
- Cause: the 30 ms housekeeping loop tested `export_btn["state"] == "disabled"`; ttk returns a Tcl object there, not a string, so the test was never true.
- Fix: the loop now restores the button by checking its text. No audio or DSP code changed. Includes the rc7 layout fix and the rc8 ruler fix.

## v2.0-rc8 - time ruler did not follow ZOOM (found at checklist M5)
- Bug: ZOOM + / ZOOM - rescaled the waveform clips but not the time ruler, so after zooming the ruler showed wrong times (a 5.44 s clip looked 13 s long).
- Fix: the ruler now redraws on every zoom change (`self.view.add_listener(self.ruler.redraw)`). Click-to-seek was already correct. No audio or DSP code changed.
- Also includes the rc7 layout fix below.

## v2.0-rc7 - track rows were hidden on small screens (found at checklist M5)
- Bug: on a 1440x900 screen the timeline area shrank to just the ruler, so the track rows (name, ARM, FX, waveform) were not visible and a track could not be armed.
- Fix: the timeline row now keeps a minimum height of 190 px (one full track row, ruler and scrollbar), and the Debug Center tabs are shorter (4 rows instead of 7). No audio or DSP code changed.
- Tip: the green hint banner at the top can be closed with "Got it" to free more room.

## v2.0-rc6 - AUTO picked the wrong input device (found at checklist M2)
- Bug: with a USB webcam microphone plugged in, AUTO selected it as the input (it was the first WASAPI input in the list and only supports 16000 Hz), so MOUNT failed with `Invalid sample rate` in every mode. Cause: the "default device" flags only knew the MME default, which never matches a WASAPI device, and the name fallback failed because MME cuts names at 31 characters. The soak tool was not affected because it asks WASAPI for its own default devices.
- Fix: the default flags now cover the default device of every host API (`settings_store.default_device_ids`, used by `AudioEngine.probe_all_devices`), and the name fallback also matches MME-shortened names. The Devices tab now shows DEFAULT-IN / DEFAULT-OUT for each driver's default.
- README troubleshooting: row for `Invalid sample rate`.
- tests: 161 (unittest OK), 5 new regression tests in tests/test_phase7c.py using the real device list from the user's PC.

## v2.0-rc5 - power plan found, safe block size chosen
- Root cause of the live-only dropouts: the Windows **Balanced** power plan. With High performance, the rc4 code passes: 5 of 5 one-minute experiments clean, and 10-minute soaks with all effects: block 256 = 0 late blocks (twice), block 128 = 6-7 late blocks in 225,000, block 64 = 9 in 450,018.
- Measured round trip (cable calibration): 9.60 ms at block 128, 12.29 ms at block 256.
- 10-minute soak, block 128, typical effects: 0 late blocks in 225,023 (13.6 % CPU).
- AUTO and the default block size are now **128** (was 64). Settings saved by older versions keep their block size until AUTO is pressed.
- New `power_plan.py`: after MOUNT the app reads the Windows power plan and logs a WARN if it is Balanced or Power saver. It never changes the plan. The debug report has a `Power plan:` line.
- README: power plan section with the measured table, `--fx` soak option, updated troubleshooting.
- tests: 156 (unittest OK on the real PC, 0 skipped), new tests/test_phase7c.py. Two Tk panel tests that assumed the old default block 64 were updated to 128.
- Not changed: DSP code and effect behaviour, process priority/timer tuning (no measurable gain). Not done: RTT at block 64, 10-minute typical-effects soak at block 64, manual checklist M1-M13 on the real PC (mostly), PyInstaller build.

## v2.0-rc4 - first real speed-ups (DSP) and engine-only test
- Round-1 live experiments (switch interval, process priority, 1 ms timer) did not help. The priority option had a bug (did not apply) and is fixed (proper ctypes types).
- Reverb: combs now process the whole block and each all-pass is chunked by its own delay length (same samples as before, 12 -> 7 Python calls per block at block 128). dsp_bench reverb 1.4 % -> 1.0 % at block 128.
- Compressor: REFINE 2 -> 1 (about 20 % faster). Max error vs the v1.1 reference stays below -99 dBFS on noise, bursts, clicks, level steps and a square wave (test limit -60 dBFS).
- `tools/soak_test.py --fx none|typical|all` (all start from every effect OFF). `none` measures the engine alone. New `run_experiments2.bat`.
- tests: 149 (unittest OK).

## v2.0-rc3 - live speed experiments
- Profiler on a real PC: offline callback is steady (1.11 ms at block 128, no spikes, GC not the cause); the live soak is twice as slow with spikes, so the cause is live-only.
- `tools/soak_test.py` live options: `--switch-interval`, `--priority high`, `--timer1`. New `run_experiments.bat`. tests/test_phase7.py: tuning test (146 tests).
- Still not fixed: live soak fails at blocks 64/128/256.

## v2.0-rc2 - performance diagnostics (after the first live soak FAILED on a real PC)
- Live soak at block 64/128/256 failed (see HANDOFF_phase7b_live_soak.md). New `tools/profile_callback.py`, `run_diagnostics.bat`, `run_soak.bat`.
- Tests: unclosed-file warnings fixed. docs/ now holds the Developer Guide.
- The performance fix itself is NOT done yet (next session).

## v2.0 - Phase 7 (final QA, packaging, docs)
- Version 2.0 everywhere: one `version.py`, shown in the window title and the debug report. Project files get an `app_version` stamp (file format version is unchanged; v1.x files still load).
- New `tools/soak_test.py`: 4 takes recorded and overdubbed, all effects on every track and the master bus. `--offline` checks CPU headroom without a sound card; `--live` uses the real sound card (WASAPI exclusive 48000/64) and judges xruns. Exit code 0 = PASS.
- `latency_lab.py dsp-bench`: the literal `%%` in the two heading lines now prints `%`.
- New `run_looper.bat` (checks Python 3.10+, installs requirements, starts the app, writes `logs\launcher.log` on failure).
- README rewritten for v2.0: install, exclusive mode and its side effects, GUI tour, calibration, Debug Center, troubleshooting table, how to run tests and the soak test.
- New `docs/QA_RESULTS.md`: automated results filled in, manual checklist M1-M11 and the real-PC soak left for the user to tick.
- tests/test_phase7.py.
- Not done on purpose: PyInstaller build (needs a Windows machine; see README).

## Phase 6 - Debug Center and logging
- New `debug_log.py` (pure Python): levels DEBUG/INFO/WARN/ERROR/CRIT, ring buffer (last 2,000 lines), rotating file `logs/looper.log`, `log_rt()` for the audio callback (only counts; the GUI turns counts into lines), debug report builder, global exception handler, test-signal generator.
- New `debug_center.py`: panel [4] is now a DEBUG CENTER with tabs Log (level filter + search, coloured), Engine (live values), Devices (inventory + Rescan), Tracks (length, offset, effects on, estimated CPU).
- COPY DEBUG REPORT: clipboard + `logs/report_<time>.txt` (versions, settings, engine, telemetry, calibration, devices, last 100 log lines).
- Errors in the GUI or in threads are written to the log with traceback and shown as a short message; the app keeps running.
- F12 shows a test signal bar (sine 440 Hz / noise, level 0.1) that plays instead of the looper mix, no cable needed. It stops on UNMOUNT.
- `app.log()` keeps its signature; every line now also goes to the file. Audio callback counts PortAudio status flags via `log_rt`.
- tests/test_phase6.py (16 tests).

## Phase 5 - in-app latency calibration
- New `latency_core.py`: chirp, analysis and verdict code moved out of `latency_lab.py` (CLI now imports it: one copy).
- `AudioEngine.run_calibration()`, `set_calibration()`, `measured_rtt_ms()`; log lines `[CALIB] ...`.
- Panel [1]: CALIBRATE LATENCY button + result card (RTT, jitter, level dBFS, status OK / TOO QUIET / CLIPPING / NO SIGNAL).
- Good result is saved in settings.json (`calibration`), fills Record offset and `engine.record_latency_samples`.
- Status line: `RTT x ms (measured)` in blue when calibrated for the running mode, else grey `(reported, not measured)`.
- tests/test_phase5.py (14 tests). 4a status-text test updated for the new label.

## v1.2-dev — Phase 4b (audio settings panel + settings.json)

- New panel [1] `audio_settings_panel.py`: Driver, Exclusive/Shared, sample rate (44100/48000), block size (32-512), input/output lists filtered by the chosen driver, **Record offset (ms)**, **AUTO (recommended)** button (WASAPI exclusive 48000 / 64 + Windows default devices), MOUNT button. Exclusive is only offered on WASAPI. The sample-rate box is locked while tracks exist.
- Changing a setting while mounted asks "unmount and mount again now?"; "No" puts the old value back. Changing only the record offset never asks.
- Record offset (ms) is converted to samples when you press RECORD and feeds `engine.record_latency_samples` (log: `[LOOPER] Record offset compensated by ... ms`).
- New `settings_store.py` (pure Python): `settings.json` next to `main.py` stores driver, mode, rate, block, record offset and the device NAMES (ids change between boots). Missing or broken files and bad values are ignored per key. Saved on mount, on a settings change and on close; used to preselect everything at start.
- Project files get an `audio` section (`sample_rate`, `block_size`). Old files load with defaults. Loading a project while unmounted switches the engine rate to the project's rate.
- Tests: `tests/test_phase4b.py` (21 tests, 4 of them a real-Tk smoke test that is skipped where Tk is missing). Total 107.

## v1.2-dev — Phase 4a (telemetry + status line + load graph)

- New `telemetry.py`: the audio callback times itself (`time.perf_counter`) and stores last / average / worst callback time, a 100-block history, and counters for xruns (input/output underflow/overflow flags from PortAudio) and overruns (callback slower than the block). Plain numbers only, read by the GUI without a lock.
- The callback no longer writes a log line for stream status (it only counts); the GUI logs at most one `[AUDIO] N dropout(s) ...` line per 150 ms tick.
- `engine.cpu_load()` (our measure: callback time / block time) and `engine.pa_cpu_load()` (PortAudio's own figure).
- Status line under the meters: `WASAPI EXCL 48000/64 | RTT 15.2 ms (reported) | CPU 12% | xruns 0 | peak 0.42`. It turns red above 70 % CPU or when the output peak is 0.85+. RTT stays labelled "reported" until Phase 5 measures it.
- New LOAD graph (beside the meters): one bar per block, full height = 150 % of block time, red line = 100 %, bars above 70 % are red.
- Tests: `tests/test_phase4a.py` (13 tests). Total 86.
- Still to do in Phase 4b: audio settings panel, `settings.json`, `audio` section in project files, record-offset field.

## v1.2-dev — Phase 3 (DSP vectorization)

- `Delay`: slice reads/writes on the circular buffer, no per-sample loop (chunked only if the delay is shorter than the block). Output identical to v1.1.
- `Reverb`: every comb and all-pass line is processed with slices (blocks longer than the shortest line, 81 samples, are split into chunks); the damping low-pass uses `scipy.signal.lfilter` with carried state. Output matches v1.1 to about -145 dBFS.
- `Reverb.set_room_size()` and `from_dict()` no longer rebuild or zero the buffers (fixes the click when moving the slider and a cut tail). They change a float and set a flag; the audio thread applies the new comb feedback at the start of its next block. `Reverb.reset()` is the only way to clear a tail.
- `Compressor`: same envelope maths, solved per block with `cumprod`/`cumsum` (attack/release choice estimated, then refined twice) and vectorized gain. Matches v1.1 exactly on the golden test.
- Safety clamps: delay feedback max 0.98, reverb damping/room size 0..1, compressor ratio at least 1. Extreme settings no longer give NaN/inf.
- Master bus keeps two chains (L and R); with vectorized effects the extra cost is small.
- `effects.benchmark_costs()` + new `tools/dsp_bench.py`; FX dialog shows a "CPU cost" line on every tab.
- Whole chain, all effects on, block 64: about 9.6% of block time (was about 87%). Measured in the build sandbox, re-check on your PC.
- Tests: `tests/test_phase3.py` (11 tests), `tests/reference_dsp.py` (the old v1.1 loops, tests only). Total 73 tests.

## v1.2-dev — Phase 2 (callback safety + recording compensation)

- Audio callback no longer takes `engine.lock`. It reads one immutable tuple of tracks (`_tracks_view`); add/remove/load swap that tuple. `engine.tracks` still works (returns a list copy; assigning a list swaps the snapshot).
- Recording buffer is pre-allocated (5 min) when RECORD starts; stopping a take trims it (no `np.concatenate`). `engine.housekeeping()` (called by the UI timer) enlarges it by doubling off the audio thread; the callback only grows it as a last resort, losing no audio.
- Callback scratch arrays (`mix_l`, `mix_r`, input copy) are allocated once per block size.
- New `engine.record_latency_samples`: new takes are anchored `latency` samples earlier on the timeline (head trimmed if that is before time 0). Log: `[LOOPER] Record offset compensated by 8.2 ms`. Phase 4 adds the field to type it in, Phase 5 fills it from calibration.
- Delay/reverb tails keep ringing when a clip's audio ends or goes silent (`track.tail_samples_left`).
- Tests: `tests/test_phase2.py` (11 tests: lock not needed, 10,000-block stress with UI calls from a second thread, recording buffer, compensation, tails).

## v1.2-dev — Phase 1 (exclusive-mode engine)

- New `stream_config.py`: `StreamConfig` and the fallback ladder (exclusive at chosen rate -> exclusive at other rate -> shared 48000 -> clear error).
- `AudioEngine.open_stream(in, out, cfg=None)` now opens WASAPI exclusive (`latency="low"`, mono in / stereo out) and logs every step, e.g. `[AUDIO] Trying exclusive 48000/64 ... OK`.
- Exclusive needs both devices on WASAPI; this is checked first and explained in the log.
- Engine sample rate only changes when no tracks exist; master FX are rebuilt at the new rate.
- `engine.mode_name` / `engine.active_config` added; status bar shows the mode. Default block size is now 64.
- App preselects the WASAPI default devices.
- Tests: `tests/test_stream_ladder.py` (13 tests, mocked sounddevice).

## v1.2-dev — Phase 0 (test safety net)

- Added `tests/` (38 tests): recording, playback, pan/gain/mute/solo, loop wrap, offline render vs live callback, project save/load, effects behaviour, golden DSP comparison.
- Added `tests/fake_stream.py` to drive the audio callback with no sound card, and `tests/_stubs.py` to run without PortAudio.
- Added `tools/golden.py` and `tests/golden/baseline_dsp.npz` (reference output of the v1.1 effects).
- No application code changed.

## v1.1 — Production / UX pass

### Bugs fixed (confirmed with automated regression tests, see below)

1. **Recording data-loss on arm/unarm.** Arming a different track (or
   un-arming one) while a track was mid-recording used to wipe the take
   with `track.recording = False` instead of committing it. Now every
   arm/unarm path routes through `Track.stop_recording()`, so the buffer is
   always saved first.
2. **Master bus effects were mostly decorative.** The compressor,
   distortion, delay and reverb on the Master FX rack were fully modeled,
   editable, and saved/loaded — but the realtime callback and the offline
   exporter only ever ran the EQ stage. Turning on master compression or
   reverb audibly did nothing. Both paths now run the full chain.
3. **Mounting the engine silently started playback.** `open_stream()` used
   to set `is_playing = True`, so the very first press of "PLAY" (which
   still read "PLAY") actually *stopped* the transport. Mounting now only
   starts the I/O stream; the transport stays stopped until you press PLAY.
4. **Solo was ignored on export.** The live engine correctly muted
   non-soloed tracks, but `render_mix()` (used by EXPORT MIX) always
   rendered every unmuted track regardless of solo, so a soloed preview
   never matched the exported file. Export now mirrors solo exactly.
5. **Timeline ruler stopped tracking scroll position.** `TimelineRuler` had
   no `scrollregion` configured, so calling `xview()` on it to keep it in
   sync with the waveform area was a silent no-op — scrolling right showed
   the wrong time markers and ruler-click-to-seek landed in the wrong spot.
6. **Per-track controls scrolled out of view.** Arm/mute/solo/FX/volume/pan
   used to live inside the same horizontally-scrolling strip as the
   waveform, so scrolling right on a long arrangement scrolled your mixing
   controls away too. Controls now live in a frozen header column that only
   scrolls vertically; the waveform area scrolls independently.
7. **FX sliders that appeared to do nothing.** Every effect except EQ starts
   disabled, and the only way to turn one on was a separate, easy-to-miss
   checkbox above the sliders — moving a knob and hearing nothing is the
   #1 "this feels broken" complaint for a rack like this. Touching any
   slider for an effect now auto-enables it (and ticks its checkbox).
8. **Stale checkboxes after arming.** Arming one track auto-unarms every
   other track in the engine, but the other tracks' ARM checkboxes stayed
   visually checked. Every track strip now re-syncs from the model whenever
   any track's state changes.
9. **Recording without pressing Play first recorded in isolation.** You
   could hit RECORD without PLAY; capture worked, but the playhead never
   advanced and existing tracks never played back, so overdubbing was
   impossible without a separate manual PLAY press first. `RECORD ARMED`
   now starts the transport automatically if it isn't already running.
10. **Duplicate FX windows.** Clicking `FX` on a track (or `MASTER FX`)
    twice used to spawn two separate windows editing the same effect state.
    Opening FX on a track/bus that's already open now just focuses the
    existing window.
11. **Race conditions on save / export.** `save_project()` and the export
    worker thread used to read `engine.tracks` directly while the realtime
    audio thread could be mutating it (adding a track, committing a
    recording). Both now take a locked snapshot first.

### New in this pass (production-readiness / usability)

- **REWIND** button + `Home` shortcut.
- **NEW PROJECT** button to start fresh without restarting the app.
- **Getting-started banner** spelling out the exact first-run click order
  (device → mount → add track → arm → record), dismissible.
- **Live numeric readouts** for each track's Volume/Pan sliders (previously
  no way to see the exact value).
- **Empty-state messaging**: "No tracks yet" placeholder in the timeline,
  and "Empty — ARM this track, then hit RECORD ARMED" on blank track
  waveforms, so a new user isn't looking at a blank canvas with no hint.
  The PLAY button also self-corrects if the transport starts/stops from
  something other than the button itself (e.g. auto-play on record).
- **Track count indicator** next to the level meters.
- **Keyboard shortcuts**: `Space` (Play/Stop), `R` (Record), `Home`
  (Rewind) — automatically disabled while typing in a track name field.
- Minor lint cleanup (unused `lfilter_zi` import).

### How this was verified

Per the request, the app was **not** run interactively in this environment
(no audio hardware / display here). Instead:

- Every module was syntax-checked (`py_compile`) and linted (`pyflakes`,
  clean).
- All engine, track, effects, and project I/O logic was exercised with a
  real `sounddevice`/`numpy`/`scipy`/`soundfile` install and a dedicated
  regression script covering each bug above (arm-mid-recording, master FX
  chain, solo-on-export, rewind, save/load round-trip with effect state,
  new-project/snapshotting) — all passing.
- The GUI modules (`app.py`, `waveform_widget.py`, `fx_dialog.py`) were
  statically checked for structural consistency (every referenced method
  has a matching definition) since a live Tk session isn't meaningful
  without a real display or audio device on your end.

You should still do a quick smoke test on your machine (mount a device,
add a track, record a few seconds, export) before relying on it live.
