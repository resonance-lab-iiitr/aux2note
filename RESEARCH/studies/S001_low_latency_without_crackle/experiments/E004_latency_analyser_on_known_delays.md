# E004 : Latency analyser on known delays

ID: E004
Study: S001
Stage: 0
Kind: calibration
Status: planned
Tests: H005,H006
Registered: 2026-11-14
Repeats: 20
Script: RESEARCH/studies/S001_low_latency_without_crackle/scripts/e004_latency_analyser_on_known_delays.py
Outputs: results/E004_<run>.zip
Pass rule: Part A (analyze): synthetic loopback recordings with a KNOWN delay. In every cell with SNR 20 dB or more, in all 20 seeds: all 6 bursts detected and the mean measured delay within 0.05 ms of the true delay; for true delays 19.90 ms and 20.10 ms the verdict "at or below 20.0 ms" is right in 20 of 20 seeds; noise only (no chirp) reports all 6 bursts missed in 20 of 20 seeds. Part B (Calibrator callback logic): a simulated duplex stream with a known delay of D samples, driven block by block, gives rtt_samples equal to D within 1 sample in every cell. Part C (status words): summarize() returns OK for captured peak 0.4 and 0.02, TOO QUIET for peak 0.005, CLIPPING for peak 0.99, NO SIGNAL for noise only.
Fail rule: Any cell with SNR 20 dB or more where, in any seed, the error exceeds 0.10 ms, or 2 or more seeds of one cell miss a burst; or any Part B cell off by more than 2 samples; or a wrong 20.0 ms verdict at 19.90 / 20.10 ms in any seed; or any wrong status word in Part C. A fail means a tool defect: a new task and a new calibration card, and no latency number counts until it passes.
Changed: the known delay (true_ms, fractional samples included). Part B changes the block size and D.
Held fixed: latency_core.py as in CODE at T031 (sha256 recorded in the pack), chirp 30 ms 300 to 12000 Hz, 6 bursts, ncc_min 0.35, sample rates 44100 and 48000, recorded level 0.4.
Controls: noise-only recordings (Part A and C); a delay of 0 ms cell; the same synthetic file analysed twice must give identical numbers (determinism).
Metrics: err_ms_max (per cell, ms), missed_bursts (count), class_correct_rate (0 to 1), rtt_samples_error (samples, Part B), status_ok (count of right status words), n_cells, n_seeds.
Confounds: the synthetic delay is an ideal frequency-domain shift, so this checks the arithmetic of finding the chirp position, not what a real converter adds (that delay IS part of the real RTT and cannot be separated); the white noise of the recording is not the sound card's noise; clock drift between ADC and DAC is not modelled (the Realtek runs both on one clock; a USB device would not); latency_lab.run_one has its own callback copy of the Calibrator logic, covered by the same cells but not the same code.
Notes to record: none (sandbox run). If the owner repeats it on his PC: Python and numpy versions.

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
1. R-BUILD writes the script: it imports latency_core read-only from CODE/ and builds the cells; `--selftest` is the whole experiment (no hardware). Cells for Part A: fs {44100, 48000} x true delay {0, 3.3, 9.99, 17.77, 19.90, 20.10, 49.0, 212.4} ms x recording SNR {40 dB, 20 dB} x {clean converter, converter-like: low-pass 15 kHz + DC 0.01 + 50 Hz hum 0.01} x seeds 1..20 (random fractional offset and noise).
2. Part B: a loop that mimics a duplex stream block by block (output block k becomes input D samples later) for blocks {32, 64, 100, 128, 144, 160, 256, 288, 333, 512} and D {0, 1, 97, 960, 1013, 2000}; drive Calibrator.process() and read result()['rtt_samples'].
3. Part C: summarize() on scaled copies of one clean recording.
4. Build the result pack with RESEARCH/lib/rpack.py and run `rpack.py check`.

## Analysis plan
Per cell: max absolute error over the 20 seeds; count of missed bursts; for the 20 ms boundary cells the share of correct verdicts. Verdict = the pass and fail rule above exactly; a cell between 0.05 and 0.10 ms or with exactly 1 missed burst in 1 seed is INCONCLUSIVE: rerun with 100 seeds before deciding. Determinism and noise-only controls are reported first. If it passes, STUDY.md Instrument records "latency analysis arithmetic validated on synthetic delays (E004)".

## Results
[Filled in R-ANALYZE only. One table row per run.]
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
