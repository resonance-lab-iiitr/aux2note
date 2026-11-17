# Verdict: software_scheduling (confidence medium)

Most likely: software_scheduling (confidence medium). 14 of 14 events sit at the start of the 128-sample block (offset 0, R=1.00, p=4.8e-10).

## Evidence
- 14 of 14 events sit at the start of the 128-sample block (offset 0, R=1.00, p=4.8e-10).

## Next test
Record the same 60 s again with a larger block (256, then 512) in the same driver mode, and with the Windows power plan on High performance. If the clicks and late blocks disappear or drop sharply, scheduling is the cause.

## Other hypotheses
- electrical (medium): 50 Hz hum with 7 distinct harmonic(s), strongest -82.2 dBFS.

## Numbers
- Input: sample_clicks_at_block_starts.wav (file), 5.0 s at 48000 Hz, channel 0 of 1, block size 128.
- Clicks: 14 (168.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0000 (-89.0 dBFS). Noise floor -17.1 dBFS (no quiet parts, not meaningful).
- Hum: 50 Hz, 7 distinct harmonic(s), strongest -82.2 dBFS.
- Position in the block: 14 events, preferred offset 0.0 of 128, R=1.00, p=0.0000, clustered=yes.

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 906.7 | 0.197 | 3 |  | 0 |  | high |
| 02 | click | 4106.7 | 0.198 | 3 |  | 0 |  | high |
| 03 | click | 2506.7 | 0.197 | 3 |  | 0 |  | high |
| 04 | click | 3146.7 | 0.193 | 3 |  | 0 |  | high |
| 05 | click | 1546.7 | 0.192 | 3 |  | 0 |  | high |
| 06 | click | 3466.7 | 0.216 | 3 |  | 0 |  | high |
| 07 | click | 586.7 | 0.222 | 3 |  | 0 |  | high |
| 08 | click | 266.7 | 0.216 | 3 |  | 0 |  | high |
| 09 | click | 2186.7 | 0.222 | 3 |  | 0 |  | high |
| 10 | click | 3786.7 | 0.222 | 3 |  | 0 |  | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 5000 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (2 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- No blocks.csv.gz: correlation with late blocks, status flags and ADC-time gaps was not possible, so a scheduling cause cannot be ruled in or out by timing.
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
