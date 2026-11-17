# E005 : Crackle detector on injected bursts

ID: E005
Study: S001
Stage: 0
Kind: calibration
Status: planned
Tests: H001,H003
Registered: 2026-11-14
Repeats: 5
Script: RESEARCH/studies/S001_low_latency_without_crackle/scripts/e005_crackle_detector_on_injected_bursts.py
Outputs: results/E005_<run>.zip
Pass rule: Detector under test = the tone-residual burst counter of spikes/legacy_replay_burst_grid.py (reproduces analyze_lab_captures.py to the decimal, F-23): one sine fit after 1 s, bad samples = residual above 0.02, bad samples closer than 20 samples form one burst. Set A (detection, 540 synthetic captures): in every cell (tone, width, amplitude, rate) with burst peak amplitude 0.05 or more, mean over 5 seeds of recall is 0.95 or more, precision is 0.95 or more, and the estimated bursts per second is within 5 % of the injected rate. Set B (clean, 30 captures): 0 bursts in 30 of 30. Set D (grid artefact): random burst starts give phase concentration R below 0.10 at P = 144 samples in 10 of 10 captures; bursts injected on a fixed 144-sample grid give R of 0.90 or more in 10 of 10.
Fail rule: Recall below 0.80 in any cell with amplitude 0.10 or more; or 3 or more of the 30 clean captures contain a false burst; or R at P = 144 is 0.20 or more for any random-start capture; or R for the fixed-grid captures is below 0.50 (the test cannot see a grid). A fail means the detector or the grid test is a tool defect: a new task or a new card, and the crackle numbers (F-03, F-11, F-21) stay at low.
Changed: burst parameters of the injected damage (width, amplitude, rate, start pattern) and the tone frequency; one factor per sub-table (Set A varies width, amplitude, rate; the tone frequency is varied in its own sub-table).
Held fixed: sample rate 48000 Hz (Set B also 44100 Hz), tone level 0.3, 20 s, noise floor set so that the residual of the clean tone is -62 dB (the clean floor measured here, F-04), minimum separation of injected bursts 25 samples, detector code and thresholds as in the spike (sha256 in the pack).
Controls: clean tone plus noise (Set B); the same detector on a tone whose frequency does not divide 144 samples (997 Hz and 1234 Hz) against 1000 Hz (3 periods = 3 ms) to see whether the grid is a tone artefact; crackle_core.detect_clicks run on the same files as information only (no pass rule: it is the app's own detector, defects D-1..D-10).
Metrics: recall, precision, bursts_per_s_est, bursts_per_s_true, err_db_est, err_db_true, false_bursts, R_144, n_captures, n_seeds.
Confounds: synthetic bursts are additive and short; real hardware damage is dropouts, repeats and clock slips that a fit may treat differently; a clock offset between generator and recorder breaks a fixed-frequency fit (Set C below is information only); detector thresholds were set on the legacy data (the spike reproduces them), so Set A tests them on new data but not on real hardware.
Notes to record: none (sandbox run).

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
1. R-BUILD writes the script (imports nothing from CODE/ except, for the information row, crackle_core read-only). Seeds 1..5.
2. Set A: tones {1000, 997, 1234} Hz x widths {3, 9, 19} samples x peak amplitudes {0.02, 0.05, 0.10, 0.27} x rates {1, 10, 70} per s x 5 seeds = 540 captures; random start times. The amplitude 0.02 row is reported (detection floor) but is not in the pass rule.
3. Set B: 3 tones x {44100, 48000} Hz x 5 seeds = 30 clean captures.
4. Set C (information only, no rule): clock offset +5 and +20 ppm, 1 % amplitude ripple, DC offset 0.01 on clean tones; report false bursts per second.
5. Set D: 70 bursts per s, width 9, amplitude 0.27, tones 1000 and 1234 Hz, 5 seeds each, once with random starts and once with starts on a 144-sample grid (plus one random offset per capture).
6. Result pack with rpack.py; `--selftest` runs everything.

## Analysis plan
Match detected bursts to injected ones within 20 samples (a burst is one injected event). Recall = matched / injected, precision = matched / detected. Report per cell mean and min over seeds. Verdict from the rules above exactly; cells with recall between 0.80 and 0.95 at amplitude 0.05 to 0.10 are INCONCLUSIVE and name a threshold-tuning task. Set C and the crackle_core row are tables only. The R test uses the circular statistic of the domain annex (R = |mean exp(2 pi i start mod P / P)|).

## Results
[Filled in R-ANALYZE only. One table row per run.]
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
