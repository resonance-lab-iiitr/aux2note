# Verdict: electrical (confidence medium)

Most likely: electrical (confidence medium). 50 Hz hum with 4 distinct harmonic(s), strongest -87.5 dBFS.

## Evidence
- 50 Hz hum with 4 distinct harmonic(s), strongest -87.5 dBFS.
- Note: 0 late block(s), 0 with PortAudio status flags, 12 ADC-time gap(s) in 3750 blocks.

## Next test
Run the interface from a different USB port or a powered hub, unplug other devices (laptop charger, monitors), use balanced cables, and record 30 s of silence again. Note whether the hum level or the DC offset changes.

## Numbers
- Input: 20261112_144533_shared256 (folder), 20.0 s at 48000 Hz, channel 0 of 1, block size 256.
- Clicks: 1 (3.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0000 (-126.4 dBFS). Noise floor -21.1 dBFS (no quiet parts, not meaningful).
- Hum: 50 Hz, 4 distinct harmonic(s), strongest -87.5 dBFS.
- Position in the block: 1 events, preferred offset 214.0 of 256, R=1.00, p=1.0000, clustered=no.
- Blocks: 3750 total, 0 late, 0 with status flags, 12 ADC-time gaps; 0 of 1 events near one (chance 1.0%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 41.8 | 0.011 | 21 | 7 | 214 | 326.208 | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 20000 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): ok.
- excerpts/event_NN.wav: +/- 1 s around the worst events (1 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
