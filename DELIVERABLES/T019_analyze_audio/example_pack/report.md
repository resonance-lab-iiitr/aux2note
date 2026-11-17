# Verdict: software_scheduling (confidence high)

Most likely: software_scheduling (confidence high). 14 of 14 events sit at the start of the 64-sample block (offset 1, R=1.00, p=4.8e-10).

## Evidence
- 14 of 14 events sit at the start of the 64-sample block (offset 1, R=1.00, p=4.8e-10).
- 14 of 14 events are in or next to a late block, status-flag block or ADC-time gap (chance level 0.5%, p=1.5e-32).
- Note: 14 late block(s), 0 with PortAudio status flags, 0 ADC-time gap(s) in 7500 blocks.

## Next test
Record the same 60 s again with a larger block (256, then 512) in the same driver mode, and with the Windows power plan on High performance. If the clicks and late blocks disappear or drop sharply, scheduling is the cause.

## Numbers
- Input: pack1 (folder), 10.0 s at 48000 Hz, channel 0 of 1, block size 64.
- Clicks: 14 (84.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0000 (-91.6 dBFS). Noise floor -13.5 dBFS (no quiet parts, not meaningful).
- Position in the block: 14 events, preferred offset 1.0 of 64, R=1.00, p=0.0000, clustered=yes.
- Blocks: 7500 total, 14 late, 0 with status flags, 0 ADC-time gaps; 14 of 14 events near one (chance 0.5%, p=0.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 8554.7 | 0.323 | 3 | 6416 | 1 | 0.021 | high |
| 02 | click | 9534.7 | 0.333 | 3 | 7151 | 1 | 0.021 | high |
| 03 | click | 1193.4 | 0.326 | 3 | 895 | 1 | 0.021 | high |
| 04 | click | 8638.7 | 0.316 | 3 | 6479 | 1 | 0.021 | high |
| 05 | click | 6402.7 | 0.336 | 3 | 4802 | 1 | 0.021 | high |
| 06 | click | 7128.0 | 0.325 | 3 | 5346 | 1 | 0.021 | high |
| 07 | click | 6010.7 | 0.275 | 3 | 4508 | 1 | 0.021 | high |
| 08 | click | 4217.4 | 0.278 | 3 | 3163 | 1 | 0.021 | high |
| 09 | click | 9093.4 | 0.326 | 3 | 6820 | 1 | 0.021 | high |
| 10 | click | 9094.7 | 0.276 | 3 | 6821 | 1 | 0.021 | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 10000 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): ok.
- excerpts/event_NN.wav: +/- 1 s around the worst events (10 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
