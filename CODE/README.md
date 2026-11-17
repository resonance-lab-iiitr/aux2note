# Live Looper Pro 2.0

A multi-track live looper / mini DAW for Windows (also runs on macOS/Linux).
Every track is an independent clip you can record, import, drag along a shared
timeline, loop on its own, mix, EQ and effect. Version 2.0 adds a low-latency
**WASAPI exclusive mode**, latency calibration, fast effects and a Debug Center.
See [`CHANGELOG.md`](CHANGELOG.md) for every change.

## 1. Quick start (Windows 10, beginner)

1. Install **Python 3.10** from python.org. In the installer tick **"Add python.exe to PATH"**.
2. Unzip this folder anywhere.
3. Double-click **`run_looper.bat`**. The first time it installs the libraries, then opens the app.

Manual way (same result):

```
pip install -r requirements.txt
python main.py
```

Notes:
- `sounddevice` ships PortAudio inside the Windows wheel. On Linux you may need `sudo apt-get install libportaudio2`.
- `lameenc` gives direct MP3 export. If it is missing, MP3 export falls back to WAV and says so in the log.

## 2. First run: get the low-latency mode

1. In panel **[1] Audio settings** press **AUTO (recommended)**. This picks WASAPI, Exclusive, 48000 Hz, block 128 and your Windows default devices. (Settings saved by an older version keep their old block size until you press AUTO.)
2. Press **MOUNT**. The status line shows e.g. `WASAPI EXCL 48000/128 | RTT 15.2 ms (reported) | CPU 12% | xruns 0 | peak 0.42`.
3. Optional but recommended: connect a cable from **Line Out to Line In**, lower the Windows playback volume, press **CALIBRATE LATENCY** and follow the dialog. A good result fills **Record offset (ms)** and turns the status line to `RTT x ms (measured)`.
4. Press **RECORD** (key `R`) to record. Overdubs now line up with the original.

### What exclusive mode means (read this)

- Your program owns the sound card. **Other programs (browser, Teams, music players) cannot play sound while the looper is mounted.** Unmount to give it back.
- Input and output must both be on WASAPI. If exclusive cannot open, the app tries the other sample rate, then shared mode (about 37 ms round trip) and logs each step as `[AUDIO] Trying ...`.
- The sample rate is fixed per project. To change it, start a **NEW PROJECT** first.
- Block size is the speed/safety trade-off. See **Windows power plan and block size** below for measured numbers. If you hear crackles, choose 256 and mount again.

### Windows power plan and block size

**Set the Windows power plan to High performance** (Control Panel > Hardware and Sound > Power Options; click "Show additional plans" if it is hidden). On the Balanced plan the CPU slows down between audio blocks; on the test PC this alone caused hundreds of late blocks, and with High performance the same test passed. The app reads the plan when you MOUNT and writes a `[AUDIO]` warning in the Log if it is Balanced or Power saver. It never changes your power plan.

Measured on one PC (Windows 10, Realtek onboard audio, High performance, WASAPI exclusive 48000 Hz, 4 tracks, 10-minute live soak):

| Block | Round trip | All effects on 4 tracks + master | Typical effects* |
| --- | --- | --- | --- |
| 64 | not measured | 9 late blocks in 450,018 (rare clicks) | 1 min clean (not run for 10 min) |
| **128 (AUTO)** | **9.6 ms** | 6 and 7 late blocks in 225,000 (rare clicks) | **0 late blocks in 225,023** |
| 256 | 12.3 ms | 0 late blocks in 112,500 (two runs) | not run |

*Typical = EQ and compressor on every track, reverb on one track, EQ on the master.

Your PC will differ. Run the soak test (section 8) and use the smallest block that gives 0 late blocks for the way you play. If you use every effect on every track and want no clicks at all, use block 256 (about 3 ms more delay).

## 3. The window

The window opens maximized (F11 toggles full screen). A **top bar** is always visible; below it are four tabs: **Tracks**, **Mixer**, **Audio**, **Debug** (switch with the mouse or `Ctrl+1` ... `Ctrl+4`).

**Top bar (every tab)**
- `PLAY` / `STOP`, `REWIND`, `RECORD ARMED` - records into every track whose `ARM` box is on, starting at the playhead; starts the transport if needed so existing tracks play while you overdub.
- Master volume slider, IN / OUT level meters, status line (mode, round-trip time, CPU %, xruns, peak).
- `MASTER FX` (the 5-stage rack on the final mix), `+ TRACK`, `IMPORT` (wav/mp3/flac/ogg/aiff), `EXPORT` (MP3 or WAV mixdown). At UI scale 130 % and above these four move to a second line so the bar still fits.
- **LOOP ARRANGEMENT** repeats the whole timeline (independent from each track's own **LOOP CLIP**).
- Menus: **File** (new / open / save project, import, export, quit) and **View** (tabs, full screen, timeline zoom, UI scale).

**Tracks tab** - the editing workspace. One row per track: name (double-click to rename), `ARM`, `M`, `S`, `LOOP`, `VOL`, `PAN`, `FX`, `X`; the waveform clip sits on a shared timeline with a time ruler and a playhead line.
- Zoom: toolbar `ZOOM -` / `ZOOM +` / `FIT`, or `Ctrl+wheel` (zooms about the mouse pointer). `ROWS -` / `ROWS +` change the height of every track row.
- Scroll: wheel = up/down, `Shift+wheel` = sideways. The view follows the playhead only while it is playing.
- Click a clip to select it (white outline); click empty space to clear. Drag it to move it; it snaps to the playhead, time 0 and the start/end of other clips (yellow dashed guide). Hold `Shift` or `Alt` while dragging to switch snapping off; `Shift+drag` moves 10 times slower. `Left` / `Right` nudge the selected clip 10 ms (`Shift`: 100 ms). Double-click a clip to open its FX dialog.
- The FX rack has EQ (5 band), Compressor, Distortion, Delay and Reverb, each with a small "CPU cost" label.

**Mixer tab** - one channel strip per track: name, `ARM` / `M` / `S`, `PAN`, vertical volume fader with a live level meter and dB readout, on/off buttons for the five effects (`EQ CMP DST DLY REV`) and an `FX...` button for the full rack. The **MASTER** strip on the right has the master fader (same value as the top-bar slider), L/R meters and `MASTER FX...`. Double-click a fader or pan knob to reset it. With many tracks use `Shift+wheel` to scroll sideways. Everything stays in step with the Tracks tab.

**Audio tab** - left: **Devices** (driver, Exclusive/Shared, sample rate, block size, input and output lists, `AUTO`, `MOUNT`) and **Calibration** (`CALIBRATE LATENCY`, Record offset in ms). Right: **Monitoring and Input** (INPUT LOOPBACK always hear the live input; OUTPUT LOOPBACK bakes what you hear into the new take; **CLEAN INPUT**, on by default, removes DC offset and gently turns down hiss between notes - untick it to hear the raw input) and a big **Live Status** (mode, round trip, CPU, dropouts, meters, LOAD graph; "not mounted" when the engine is off). Changing a setting while mounted asks to remount. Settings are remembered in `settings.json`.

**Debug tab** - sub-tabs **Log** (level chips DEBUG..CRIT, search with match count, PAUSE SCROLL, CLEAR which only clears the view), **Engine** (value cards plus the full live table), **Devices** (inventory + Rescan, click a heading to sort), **Tracks** (length, offset, effects, estimated CPU), **Load** (callback time per block, bars turn red above 70 % of the available time, the red line is 100 %; the last 100 blocks), **Report** (preview of the debug report). `COPY DEBUG REPORT` puts the full report on the clipboard and saves `logs\report_<time>.txt`.

**UI scale** - everything (fonts, track rows, ruler, mixer strips, meters, graphs) scales from 80 % to 200 %. `Ctrl+plus` (`Ctrl+=` also works) makes it 10 % larger, `Ctrl+minus` 10 % smaller, `Ctrl+0` back to 100 %; the same entries are in the View menu. The value is saved in `settings.json` and restored at start. On a 1366 px wide screen 175 % is the largest scale where the whole top bar still fits.

**F12 test signal** - plays a quiet sine or noise (no cable needed) to check that sound comes out. Keep the Windows volume low first.

## 4. File formats

- **Project (`.llproj`)** - zip with `project.json` (positions, volumes, pans, loops, all effect settings, audio rate/block, `app_version`) plus one lossless WAV per track. Files from v1.x open fine.
- **Export** - non-editable `.mp3` or `.wav` mixdown.

## 5. Troubleshooting

| What you see | Likely cause | What to do |
| --- | --- | --- |
| MOUNT says "No audio mode could be opened" | Another program is using the sound card, or input and output are not both WASAPI | Close browsers/Teams/music apps, press AUTO, MOUNT again |
| MOUNT fails in every mode with `Invalid sample rate` | The wrong input device is selected (for example a webcam microphone that only supports 16000 Hz), or another program holds the sound card | Pick the WASAPI **Line In** and WASAPI **Speakers** in the Input/Output lists, then MOUNT; close other sound programs |
| Status shows `SHARED` and RTT about 37 ms | Exclusive failed and the app fell back | Read the `[AUDIO] Trying ...` lines in the Log tab for the reason |
| No sound from other apps | Looper is mounted in exclusive mode | UNMOUNT in the looper |
| Crackles, xruns count goes up, CPU above 70 % | Windows on the Balanced power plan, or block too small for the number of effects | Set High performance (section 2), then block 256, fewer effects, close other heavy programs |
| Overdubs start late | Record offset is 0 | Run CALIBRATE LATENCY (cable) or type the offset in ms |
| CALIBRATE says TOO QUIET / NO SIGNAL | Cable not connected or volume too low | Check Line Out to Line In, raise volume a little |
| CALIBRATE says CLIPPING | Signal too loud | Lower the Windows playback volume |
| MP3 export gives a WAV | `lameenc` missing | `pip install lameenc` |
| The app shows an error message | Any unexpected error | Press COPY DEBUG REPORT and paste it to whoever helps you |

## 6. Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Play / Stop |
| `R` | Record / stop |
| `Home` | Rewind |
| `F11` | Full screen on / off |
| `F12` | Test signal |
| `Ctrl+1` ... `Ctrl+4` | Tracks / Mixer / Audio / Debug tab |
| `Ctrl+plus`, `Ctrl+minus`, `Ctrl+0` | UI scale larger / smaller / 100 % |
| `Ctrl+N`, `Ctrl+O`, `Ctrl+S` | New / open / save project |
| `Ctrl+wheel`, `Shift+wheel` (Tracks tab) | Zoom timeline / scroll sideways |
| `Left` / `Right` (Tracks tab, clip selected) | Nudge clip 10 ms (`Shift`: 100 ms) |

Shortcuts are off while you type in a text field (for example a track name).

## 7. Project layout

```
main.py                 entry point             version.py          the version number
app.py                  main window             run_looper.bat      Windows launcher
audio_engine.py         stream, callback, transport
stream_config.py        stream settings + fallback ladder
telemetry.py            callback timing, xruns, status text
audio_settings_panel.py audio panel widget      settings_store.py   settings.json (incl. ui_scale)
latency_core.py         chirp + analysis (shared by app and CLI)
latency_lab.py          command-line latency tester and dsp-bench
debug_log.py            log ring buffer, file log, debug report
debug_center.py         Debug Center widget
tabs.py  tab_tracks.py  tab_mixer.py  tab_audio.py  tab_debug.py   the four tabs
tab_lab.py  crackle_core.py  crackle_report.py  run_crackle_matrix.bat   Crackle Lab (fifth tab), analysis, matrix
ui_theme.py  scroll_frame.py  timeline_view.py                theme, scrolling, zoom model
track.py  effects.py  fx_dialog.py  waveform_widget.py  project_io.py
tests/                  automated tests          tools/   golden.py, dsp_bench.py, soak_test.py
docs/QA_RESULTS.md      release checklist and results
```

## 8. Tests and soak test

No sound card needed for the tests. Use `unittest`, not pytest (pytest crashed on the test PC). Window tests need Tk and a display; without them they are skipped. The last full run (end of T016) was 373 tests OK.

```
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .
```

Soak test (record 4 tracks, all effects on, N minutes):

```
python tools\soak_test.py --offline --minutes 10      (CPU headroom, no sound card)
python tools\soak_test.py --live --minutes 10         (real sound card, judges xruns)
```

Easy way on Windows: double-click `run_soak.bat` (or `run_soak.bat 128 2` in a terminal for block 128, 2 minutes), and `run_diagnostics.bat` for the performance profile. Both save their output in `logs\`.

`tools\profile_callback.py` shows where the audio callback spends its time (cost over time, spikes, top functions).

`--live` is the real pass/fail: it needs **0 overruns** at the chosen block size (the `overruns` number is the real failure count; `xruns` stays 0 in exclusive mode even when blocks are late). If it fails, use the next bigger block.

To test lighter effect loads, run the script directly (the .bat file does not pass this option):

```
python tools\soak_test.py --live --minutes 10 --block 128 --fx typical
```

`--fx` accepts `all` (default), `typical` or `none`. Close the looper window first: exclusive mode blocks the sound card.

## 9. Known limitations

- The DSP is Python/NumPy/SciPy. Effects were vectorized in 2.0, but a slow PC with many tracks and all effects on may still need block 256 (see the measured table in section 2).
- The compressor envelope is computed per small sub-block (a tiny audible difference from v1.1).
- Recording and a track's own LOOP CLIP are mutually exclusive at the same moment: record first, then switch LOOP CLIP on.
- Exclusive mode blocks other apps while mounted (by design).
- No PyInstaller build is shipped. To make one on Windows: `pip install pyinstaller` then `pyinstaller --onedir --windowed main.py`, and test it on a second PC before sharing.

## 10. Crackle Lab

The app has a fifth tab, **Lab** (Ctrl+5), that records the exact sound card input and the block timing, then analyses clicks, dropouts, clipping, DC and hum. `run_crackle_matrix.bat --quick` repeats the test in several driver modes. Attach the resulting `analysis_pack.zip` (or `matrix_summary.md`) to a Claude chat. Nothing has run on a real sound card yet. Full guide: `docs/CRACKLE_LAB.md`.
