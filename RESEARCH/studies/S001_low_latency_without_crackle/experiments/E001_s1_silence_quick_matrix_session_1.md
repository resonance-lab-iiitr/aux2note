# E001 : S1 silence quick matrix (session 1)

ID: E001
Study: S001
Stage: 2
Kind: calibration
Status: analyzed
Tests: none
Retroactive: yes
Registered: 2026-11-14
Repeats: 1
Script: none
Outputs: legacy: matrix_S1 (summary, per-run folders, console text, 6 Windows screenshots)
Pass rule: legacy: not pre-registered. Original reading: clicks/min and verdict text from crackle_core (a hypothesis, not proof).
Fail rule: legacy: not pre-registered.
Changed: Mode and block (quick matrix: MME 128/256; WASAPI shared and exclusive at 48000 failed to open). Not a single-variable design.
Held fixed: 48000 Hz, 20 s per run, nothing playing, input = whatever Windows had as default (probably the USB webcam microphone), effects off.
Controls: none (no known-good input; no second device).
Metrics: clicks_per_min (crackle_core), drop, xruns, p99 callback ms, verdict text; plus analysis_output.txt: zero_fraction_first_100ms, rms after 1 s, clicks_before_200ms.
Confounds: Input device was probably the webcam microphone (F-14), not the Line In; digital silence makes the click detector fire on 1-2 LSB steps (F-07 / D-1); start-up thump in the first 200 ms; 4 of 6 runs did not open (WASAPI -9997 Invalid sample rate).
Notes to record: none (owner notes.txt was not supplied).

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
Legacy run, 2026-11-12 14:17 to 14:24: `run_crackle_matrix.bat --scenarios S1 --quick` on the owner PC (steps are not recorded in more detail; see evidence console 02).

## Analysis plan
Legacy: read from matrix_summary.md and analysis_output.txt. Only the 2 MME runs opened, so this experiment cannot say anything about WASAPI. It stays `analyzed` as an instrument-defect record (F-06, F-07, F-14), not as a measurement of the Realtek.

## Results
Legacy evidence, filed by R-IMPORT 2026-11-14 (retroactive: confidence capped at medium; capped at low while the instrument is untrusted).
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
| S1_mme_48000_128 | MME shared 48000/128, silence, input probably webcam mic | tool clicks/min 24.49; drop 4; xruns 0; 8 clicks all in the first 200 ms; first 100 ms 77 % exact zeros then start-up thump (peak 0.0742); max click amplitude 4.6e-05 | inconclusive (false clicks in digital silence = instrument defect D-1; says nothing about the Realtek) | V001 |
| S1_mme_48000_256 | MME shared 48000/256, silence | tool clicks/min 24.49; drop 1; 8 clicks before 200 ms; peak 0.0737 | inconclusive (same) | V002 |
| (4 runs) | WASAPI shared and exclusive 128/256 | open_failed, PaErrorCode -9997 Invalid sample rate | inconclusive (not a measurement; probable cause F-14) | V003 |

Summary: n = 2 runs that opened, both MME, identical click counts (24.49/min). Nothing about WASAPI.
