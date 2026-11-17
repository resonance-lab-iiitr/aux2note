# E007 : Round trip per audio path

ID: E007
Study: S001
Stage: 1
Kind: measure
Status: planned
Tests: H005,H006
Registered: 2026-11-14
Repeats: 5
Script: RESEARCH/studies/S001_low_latency_without_crackle/scripts/e007_round_trip_per_audio_path.py
Outputs: results/E007_<run>.zip
Pass rule: Per path at block 256, 48000 Hz, latency "low" (cell = one path): the cell is usable when 5 of 5 runs have status OK, all 6 bursts detected, xruns 0, within-run range 1.0 ms or less and spread of the 5 run medians 1.0 ms or less; it reaches the goal when it is usable, every run median is 20.0 ms or less, and (mean of run medians + 3 x max(SD of run medians, 0.05 ms)) is 20.0 ms or less. H005 is supported at block 256 if at least one of WASAPI exclusive, WDM-KS, ASIO4ALL reaches the goal.
Fail rule: Every one of the usable paths WASAPI exclusive, WDM-KS, ASIO4ALL has all 5 run medians above 20.0 ms: H005 is refuted at block 256 only (smaller blocks are E008, so this alone does not close H005). A path that does not open or is not usable is reported with its error text and does not count for or against.
Changed: the audio path (host API and mode): WASAPI exclusive, WDM-KS, DirectSound, ASIO4ALL. The control cell WASAPI shared (3 runs) is the same path as E006 and only checks that nothing drifted between sessions (its run medians must lie within 1.0 ms of the E006 shared medians' range).
Held fixed: 48000 Hz, block 256, latency "low" (the value the app passes, stream_config.py), Realtek Line In and Speakers by name, cable, volume, formats, 6 bursts, sweep level 0.35, no other audio programs; one fresh process per run; cell order random with a fixed seed (written in the pack).
Controls: shared control cell (3 runs) against E006; the plugged versus unplugged check of E006 (not repeated); E004 / E006 for the instrument.
Metrics: median_ms, min_ms, max_ms, jitter_range_ms, detected, xruns, peak_dbfs, noise_dbfs, reported_ms, gap_ms, cb_max_ms, cpu_load, status, plus the exact device names and the ASIO4ALL buffer size shown in its panel.
Confounds: ASIO4ALL has its own buffer setting in its control panel that the program's block argument may not control (record what the panel shows; the measured RTT is what counts); the ASIO4ALL device must have the Realtek input and output switched on and mapped so that the green jack output is heard on the input used; WDM-KS and DirectSound may refuse 48000 Hz or block 256 (reported as not usable, not as a latency); latency_lab opens 2 input channels and the app opens 1; one block size only, so a path that needs a larger block to run is not judged here.
Notes to record: everything in E006 Notes; for ASIO4ALL: the version, the buffer size and "kernel buffers" values in its panel and which devices are ticked; any path that failed to open and the printed error; Windows volume.

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
1. Same set-up and notes as E006; E006 must be analyzed and passed first (otherwise this run may still be done, but its results count only after G001 is decided).
2. For ASIO4ALL: open its control panel from the system tray, tick only the Realtek input and output, note the buffer size shown.
3. Run the wrapper script (R-BUILD): it runs, for each path in random order, 5 runs (one process per run), then 3 shared control runs. Plain equivalent per path: `python latency_lab.py run --api "WASAPI" --in Line --out Speakers --rates 48000 --blocks 256 --latency low --repeats 1` (wrapper picks the exclusive cell), and the same with `--api "WDM-KS"`, `--api DirectSound`, `--api ASIO`. Exact commands in the run sheet.
4. Attach the result zip and the latest project zip; paste the standard prompt with `mode: r-analyze`.

## Analysis plan
Table per path: n, median of run medians, min, max, SD, spread, within-run range, xruns, status; "usable" and "reaches goal" decided with the rule above; the margin 20.0 minus (mean + 3 SD) is printed. The shared control against E006. Paths that did not open: error text and an advice line. The path ranking by median RTT among usable paths feeds the selection rule of E008.

## Results
[Filled in R-ANALYZE only. One table row per run.]
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
