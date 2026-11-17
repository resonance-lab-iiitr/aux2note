# E006 : Latency repeatability on the control paths

ID: E006
Study: S001
Stage: 0
Kind: calibration
Status: analyzed
Tests: H006
Registered: 2026-11-14
Repeats: 5
Script: RESEARCH/studies/S001_low_latency_without_crackle/scripts/e006_latency_repeatability_on_the_control_pat.py
Outputs: results/E006_<run>.zip
Pass rule: On both control paths, WASAPI shared and MME, each at 48000 Hz, block 256, latency "low", Line In to Speakers by cable: in 5 of 5 runs per path all 6 bursts are detected, status OK, xruns 0, captured peak between -30 and -3 dBFS, and the within-run spread (max minus min of the 6 bursts) is 3.0 ms or less; the spread of the 5 run medians (max minus min) is 1.0 ms or less on at least one of the two paths and 3.0 ms or less on both; and in the unplugged-cable control (cable pulled from Line In), 1 run per path, no burst is detected (status NO SIGNAL) in 2 of 2.
Fail rule: Any plugged run misses a burst or reports NO SIGNAL; or the spread of the 5 run medians exceeds 3.0 ms on both paths; or an unplugged-cable run detects 1 or more bursts (the "round trip" then travels by another route, for example "Listen to this device" or crosstalk). A fail means the loopback set-up or the tool is not trusted: fix the set-up (levels, device choice, listen option) and re-register a new card; no latency number counts.
Changed: nothing between the 5 runs of a cell (this is a repeatability test: only the time and a fresh process, stream open and close differ). Between cells the host API differs (shared versus MME); the unplugged run changes only the cable.
Held fixed: Realtek Line In and Speakers (named explicitly, never the webcam microphone), formats 24 bit 48000 Hz on both, exclusive options as in STUDY.md, "Listen to this device" off, Windows volume about 50 % (value recorded), latency_lab sweep level 0.35, 6 bursts per run, latency_lab 2 input and 2 output channels, no other audio programs running, same cable.
Controls: unplugged-cable run (is the sweep heard only through the cable?); shared and MME against each other (two independent software paths to the same card); E004 for the arithmetic.
Metrics: median_ms, min_ms, max_ms (per run, over the 6 bursts, ms); jitter_range_ms (max minus min within a run); run_median_spread_ms (max minus min of the 5 run medians, ms); detected (0 to 6); xruns; peak_dbfs; noise_dbfs; reported_ms; gap_ms (measured minus reported); cb_max_ms; cpu_load.
Confounds: the spread of one path mixes instrument noise with the path's own variation (the Windows mixer may add real jitter), so the pass rule asks for a tight spread on one path only; time of day and system load; a changed Windows volume between runs; the 2-channel input of latency_lab versus the app's 1-channel input.
Notes to record: Windows volume %; driver name and VERSION of Realtek (Device Manager, Sound controllers, Driver tab); device default format of Line In and Speakers; exclusive-mode options; enhancements on or off; power plan; programs that were open; time of each run; what the unplugged run printed; anything you heard.

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
1. Set up as in STUDY.md Environment constants and the checklist in notes (close other audio programs; "Listen to this device" off; cable green jack to blue jack; volume about 50 %).
2. R-BUILD provides a wrapper script (it imports latency_lab read-only from CODE/ and calls the same run_one / aggregate, one process per run). It runs, in this order: shared 5 runs, MME 5 runs, then asks you to pull the cable and runs 1 shared and 1 MME, then asks you to plug it back. The equivalent plain tool call is `python latency_lab.py run --api "WASAPI" MME --in Line --out Speakers --rates 48000 --blocks 256 --latency low --repeats 1` repeated 5 times (the wrapper skips the exclusive cell). Exact commands are fixed in the run sheet.
3. The wrapper writes notes.txt prompts and builds results/E006_<run>.zip.
4. Attach the zip with the latest project zip and paste the standard one-line prompt (mode r-analyze).

## Analysis plan
Per path: n = 5 run medians, min, max, mean, spread; within-run ranges; detection and xrun counts; the unplugged results first. Verdict = the pass rule exactly. Also report the shared and MME medians against 20 ms for H006 (not a pass condition here; H006 is decided from E006 and E008 control cells). A pass, with E004 and E005, lets G001 set Instrument trust to trusted. The spread found here is the noise level used by every later latency card.

## Results
[Filled in R-ANALYZE only. One table row per run.]
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
| shared plugged 1-5 | WASAPI shared 48000/256 low | run medians 40.744, 40.932, 40.786, 40.890, 40.786 ms; 6/6 bursts, xruns 0, peak -15.6 dBFS, within-run range 0.0 ms; n=5, min 40.744, max 40.932, mean 40.827, spread 0.188 ms | meets the plugged-run part of the pass rule | V015 |
| mme plugged 1-5 | MME 48000/256 low | run medians 127.619, 127.473, 127.494, 127.473, 127.286 ms; 6/6 bursts, xruns 0, peak -15.6 dBFS, within-run range 0.0 ms; n=5, min 127.286, max 127.619, mean 127.469, spread 0.333 ms | meets the plugged-run part of the pass rule | V015 |
| shared unplugged 1 | cable out of Line In | status FAILED, detected 0/6, error "child process produced no result" (not NO SIGNAL) | inconclusive: pass rule needs NO SIGNAL; fail rule (a burst heard) not met | V015 |
| mme unplugged 1 | cable out of Line In | status FAILED, detected 0/6, error "child process produced no result" (not NO SIGNAL) | inconclusive: same as above | V015 |

**Verdict (R-ANALYZE 2026-11-14):** the pass rule is NOT met, because the unplugged-cable control needed NO SIGNAL in 2 of 2 and got FAILED in 2 of 2. The fail rule is not met either (no burst was detected with the cable out). Result: inconclusive on the control, so E006 does not pass and Instrument trust stays untrusted. The plugged data meet their numeric conditions (spread 0.188 and 0.333 ms), but without the working control they do not show that the sweep travelled only through the cable. The script's PREVIEW line "unplugged heard nothing: yes" is wrong (F-26); the pack metrics are right. Shared about 40.8 ms and MME about 127.5 ms are against 20 ms for H006 only provisionally (low confidence). Correction: the Held-fixed line says Realtek; the driver in use is Microsoft High Definition Audio Device 10.0.19041.1 (F-27).
