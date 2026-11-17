# E003 : Lab tone capture with output capture (session 2)

ID: E003
Study: S001
Stage: 2
Kind: measure
Status: analyzed
Tests: H001,H003
Retroactive: yes
Registered: 2026-11-14
Repeats: 1
Script: none
Outputs: legacy: lab_captures_2026-11-12 (3 capture folders: raw.wav, output.wav, blocks.csv.gz, meta.json, analysis) + app log
Pass rule: legacy: not pre-registered. Proposed later (direction file): tone error better than -55 dB and 0 bursts per second in 3 consecutive 20 s captures.
Fail rule: legacy: not pre-registered.
Changed: Mode and block (exclusive 128, exclusive 256, shared 256); mount age at capture also differed (2 min 13 s, 7 s, shortly after mount).
Held fixed: 48000 Hz, Lab test tone 1000 Hz level 0.3, 20 s, output capture on, 1 input channel, effects and monitoring off, same cable and Windows formats.
Controls: output.wav (engine output buffer) captured in every run: it is the control for "is the program's own signal clean". Shared 256 is the known-good comparison.
Metrics: err_db, bursts, bursts_per_s, max_resid, median_width, median_gap_ms for raw.wav and output.wav (analyze_lab_captures.py); blocks.csv.gz: late blocks, status flags, callback ms.
Confounds: One run per cell; mount age; ANALYZE ran with the engine mounted (D-8); recordings are channel 0 only; output.wav is taken in the callback, before PortAudio conversion; Windows volume, Realtek driver version and listening impression unknown.
Notes to record: none (owner notes.txt was not supplied).

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
Legacy run, 2026-11-12 14:40 to 14:46: app v032, Lab tab, test tone, UNMOUNT before ANALYZE not followed (D-8). Timeline in report v2 section 3.

## Analysis plan
Legacy: numbers from analysis_output_lab_captures.txt, reproduced here from raw.wav (see Results).

## Results
Legacy evidence, filed by R-IMPORT 2026-11-14 (retroactive: confidence capped at medium; capped at low while the instrument is untrusted).
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
| 20261112_144217_excl128 | WASAPI exclusive 48000/128, captured 2 min 13 s after mount | raw.wav err -60.7 dB, 0 bursts; output.wav err -152.5 dB, peak 0.3000; 0 late blocks / 0 status flags | clean exclusive run (H003: the fault is not present in every exclusive capture) | V011 |
| 20261112_144415_excl256 | WASAPI exclusive 48000/256, captured 7 s after mount | raw.wav err -10.2 dB, 1382 bursts (72.7/s), max residual 0.271, median width 19 samples, median gap 9.0 ms; output.wav err -152.5 dB, 0 bursts; 0 late / 0 flags | damaged raw with clean output: supports H001 (after the engine output buffer) | V012 |
| 20261112_144533_shared256 | WASAPI shared 48000/256 | raw.wav -61.5 dB, 0 bursts; output.wav -152.5 dB | clean comparison | V013 |

Replay in this session (spikes/legacy_replay_burst_grid.py, from raw.wav): err_db, bursts, bursts/s, max residual, median width and median gap of all three captures match the legacy numbers exactly. n = 1 per setting.
New in the replay (F-21): in V012 all 1382 burst starts lie on one phase of a 144-sample (3.000 ms) grid (maximum deviation 0 samples; all 1381 gaps are multiples of 3 ms); phase concentration R = 1.000 at P = 144 vs 0.027 expected for random starts.
