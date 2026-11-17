# E002 : S3 tone loopback quick matrix (session 1)

ID: E002
Study: S001
Stage: 2
Kind: measure
Status: analyzed
Tests: H003
Retroactive: yes
Registered: 2026-11-14
Repeats: 1
Script: none
Outputs: legacy: matrix_S3 (summary, 6 per-run folders with raw.wav / output.wav / analysis, console text)
Pass rule: legacy: not pre-registered. Original reading: tone residual about -62 dB and no bursts = clean; verdict text from crackle_core.
Fail rule: legacy: not pre-registered.
Changed: Mode and block together (quick matrix: MME 128/256, WASAPI shared 128/256, WASAPI exclusive 128/256). Two variables change; each cell has one run.
Held fixed: 48000 Hz, 20 s, 1 kHz tone from the program out of Speakers via 3.5 mm cable into Line In, 1 input channel opened, effects off, Windows formats 24 bit / 48000 Hz.
Controls: No output capture in this session (output.wav was not captured, so program output vs input could not be separated here). Shared / MME act as an informal known-good comparison.
Metrics: tone residual (resid_db), clicks_per_s_after_1s, peak, tone_amp, fund_share, clicks/min from the matrix tool.
Confounds: One run per cell; exclusive runs were always after a fresh engine build; no latency measured; instrument defects D-1, D-5, D-6; owner notes.txt missing.
Notes to record: none (owner notes.txt was not supplied).

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
Legacy run, 2026-11-12 14:24 to 14:27: `run_crackle_matrix.bat --scenarios S3 --quick` after the cable was connected and Line In set as default (see screenshots in E001 evidence).

## Analysis plan
Legacy: per-run table in report v2 section 4.1. Re-analysed here from the raw recordings with the legacy script (see Results).

## Results
Legacy evidence, filed by R-IMPORT 2026-11-14 (retroactive: confidence capped at medium; capped at low while the instrument is untrusted).
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
| S3_mme_48000_128 | MME 128 | resid -62.7 dB; 0 bursts; tool clicks/min 2.99 | supports "shared / MME clean" (H003 context only) | V004 |
| S3_mme_48000_256 | MME 256 | -62.5 dB; 0 bursts; 2.99 | same | V005 |
| S3_wasapi-shared_48000_128 | WASAPI shared 128 | -62.4 dB; 0 bursts; 8.96 | same | V006 |
| S3_wasapi-shared_48000_256 | WASAPI shared 256 | -61.7 dB; 0 bursts; 8.97 | same | V007 |
| S3_wasapi-excl_48000_128 | WASAPI exclusive 128 | -8.8 dB; 143.3 clicks/s after 1 s (tool, session 1 method); replay 3881 bursts, max amplitude 0.242 | damaged (H003: one of the 3 damaged exclusive captures) | V008 |
| S3_wasapi-excl_48000_256 | WASAPI exclusive 256 | -5.2 dB; 86.6 clicks/s after 1 s; replay merges to 1 burst (damage too dense); max amplitude 0.195 | damaged | V009 |

Summary (computed here from the table): shared + MME n = 4, resid -62.7 to -61.7 dB, mean -62.3 dB; exclusive n = 2, -8.8 and -5.2 dB, mean -7.0 dB. One run per cell; mode and block both change. No output capture, so H001 is not tested by this experiment.
