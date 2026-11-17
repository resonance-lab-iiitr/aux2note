# Verdict: electrical (confidence medium)

Most likely: electrical (confidence medium). 50 Hz hum with 3 distinct harmonic(s), strongest -88.9 dBFS.

## Evidence
- 50 Hz hum with 3 distinct harmonic(s), strongest -88.9 dBFS.

## Next test
Run the interface from a different USB port or a powered hub, unplug other devices (laptop charger, monitors), use balanced cables, and record 30 s of silence again. Note whether the hum level or the DC offset changes.

## Numbers
- Input: S3_mme_48000_128 (folder), 20.1 s at 48000 Hz, channel 0 of 1, block size 128.
- Clicks: 1 (3.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset -0.0000 (-113.4 dBFS). Noise floor -21.4 dBFS (no quiet parts, not meaningful).
- Hum: 50 Hz, 3 distinct harmonic(s), strongest -88.9 dBFS.
- Position in the block: 1 events, preferred offset 117.0 of 128, R=1.00, p=1.0000, clustered=no.
- Blocks: 7520 total, 0 late, 0 with status flags, 0 ADC-time gaps; 0 of 1 events near one (chance 0.0%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 229.1 | 0.025 | 5 | 85 | 117 |  | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 20053 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (1 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
