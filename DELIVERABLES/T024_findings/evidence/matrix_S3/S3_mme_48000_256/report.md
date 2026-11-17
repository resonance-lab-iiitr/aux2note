# Verdict: electrical (confidence medium)

Most likely: electrical (confidence medium). 50 Hz hum with 3 distinct harmonic(s), strongest -88.8 dBFS.

## Evidence
- 50 Hz hum with 3 distinct harmonic(s), strongest -88.8 dBFS.

## Next test
Run the interface from a different USB port or a powered hub, unplug other devices (laptop charger, monitors), use balanced cables, and record 30 s of silence again. Note whether the hum level or the DC offset changes.

## Numbers
- Input: S3_mme_48000_256 (folder), 20.1 s at 48000 Hz, channel 0 of 1, block size 256.
- Clicks: 1 (3.0 per minute). Dropouts: 1. Clipped runs: 0.
- DC offset -0.0000 (-119.8 dBFS). Noise floor -21.4 dBFS (no quiet parts, not meaningful).
- Hum: 50 Hz, 3 distinct harmonic(s), strongest -88.8 dBFS.
- Position in the block: 2 events, preferred offset 6.5 of 256, R=0.92, p=0.1996, clustered=no.
- Blocks: 3760 total, 0 late, 0 with status flags, 0 ADC-time gaps; 0 of 2 events near one (chance 0.0%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 229.1 | 0.025 | 5 | 42 | 246 |  | high |
| 02 | dropout_repeat | 5.8 | 0.001 | 9 | 1 | 23 |  | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 20053 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (2 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
