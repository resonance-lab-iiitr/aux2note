# E008 : Round trip versus block size

ID: E008
Study: S001
Stage: 1
Kind: measure
Status: planned
Tests: H005,H008
Registered: 2026-11-14
Repeats: 5
Script: RESEARCH/studies/S001_low_latency_without_crackle/scripts/e008_round_trip_versus_block_size.py
Outputs: results/E008_<run>.zip
Pass rule: Paths measured = WASAPI exclusive plus the usable path with the lowest median RTT at block 256 in E007 if that is a different path (a second path if E007 has two usable paths below 40 ms); blocks 32, 64, 96, 128, 144, 160, 192, 256, 288 at 48000 Hz, latency "low". Cells are judged with the usable / reaches-the-goal rule of E007. H005 supported if at least one cell reaches the goal. H008 supported for a path if, over the usable cells, the ordinary least-squares slope of run medians against block time (frames / 48000 x 1000 ms) is positive with a 95 % interval above 0 and the cell medians are non-decreasing in block size within the E006 spread (1.0 ms); report slope and intercept with their intervals.
Fail rule: H005 refuted for this PC's tested paths and blocks if every usable cell has all 5 run medians above 20.0 ms (the lowest usable RTT is then the answer to stage 1 and the 20 ms goal needs another route). H008 refuted for a path if the cell medians of its usable cells differ by 1.0 ms or less across the whole sweep 64 to 288, or are not monotone beyond 1.0 ms. A block that does not open or is unstable is reported as such (not a latency).
Changed: the block size in frames (32, 64, 96, 128, 144, 160, 192, 256, 288).
Held fixed: path (per cell group), 48000 Hz, latency "low", devices by name, cable, volume, formats, sweep level 0.35, 6 bursts, one fresh process per run, cell order random with a fixed seed, no other audio programs.
Controls: WASAPI shared and MME at blocks 128 and 256, 3 runs each (H006: 3 calibrations each, as in the owner's criterion; also the drift check against E006); the 256 cell of every path against E007 (same setting, different day / session: a drift check, medians within 1.0 ms of the E007 range).
Metrics: as E007, plus block, block_ms (frames / rate), fit_slope, fit_intercept_ms, fit_slope_ci, fit_intercept_ci.
Confounds: block 144 and 288 are whole multiples of the 3.000 ms burst grid (H007), 128 and 256 are not; this card measures only latency, but a path whose RTT does not follow the block (H008 refuted) may be re-quantised by the driver; ASIO4ALL ignores or rounds the requested block (record its panel value; the measured RTT counts); stream open fallbacks inside the tool are not logged here (the printed config is recorded per run); a block that opens but runs with xruns is not usable; small blocks raise CPU load, which this tool measures with no effects loaded (the app with effects needs larger blocks, E008 says nothing about that).
Notes to record: as E006 and E007; plus any block that failed to open, any audible click you noticed during the sweep, and the ASIO4ALL panel value for every block.

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
1. E007 must be analyzed first: the paths and the control cells come from its result. R-BUILD takes the path list from the attached E007 pack (a `--paths` argument, recorded in the pack) and builds the run sheet.
2. Same set-up and notes as E006.
3. Run the wrapper: for each (path, block) in random order 5 runs (control cells 3 runs). Plain equivalent per path: `python latency_lab.py run --api "WASAPI" --in Line --out Speakers --rates 48000 --blocks 32 64 96 128 144 160 192 256 288 --latency low --repeats 1` repeated 5 times (wrapper selects exclusive and shared cells). About 100 runs of about 7 s each.
4. Attach the zip and the latest project zip; paste the standard prompt with `mode: r-analyze`.

## Analysis plan
Per cell: n, median of run medians, min, max, SD, spread, within-run range, xruns, status. Figure (script in spikes/): RTT versus block time per path with the fitted line and a 20 ms line, run points shown. Fit per path with ordinary least squares on run medians of usable cells (n = number of runs, not bursts, because bursts within a run are correlated); 95 % interval by the t distribution on the run-level fit. The lowest usable RTT = minimum over usable cells of the median of the run medians, reported with min and max. Verdicts by the rules above; G002 applies its own rule on the same numbers. A cell with some run medians at or below 20.0 ms and some above is INCONCLUSIVE: 10 more runs there before any decision.

## Results
[Filled in R-ANALYZE only. One table row per run.]
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
