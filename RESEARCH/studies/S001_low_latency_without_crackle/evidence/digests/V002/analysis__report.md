# Verdict: hardware_or_driver_input (confidence high)

Most likely: hardware_or_driver_input (confidence high). 8 click(s), 24.5 per minute, at random positions inside the block (no fixed offset).

## Evidence
- 8 click(s), 24.5 per minute, at random positions inside the block (no fixed offset).
- The capture was made with nothing playing / effects and monitoring off, so the clicks were not produced by the program's own sound.
- No late block, status flag or ADC-time gap in 3675 blocks.
- The clicks are present in the raw sound-card capture, before any DSP.

## Next test
Record 60 s of the RAW input with effects and monitoring off and nothing playing, then repeat with another USB port / cable and in another driver (WASAPI exclusive, ASIO). Clicks at the same rate in every engine mode point at the interface or its driver.

## Numbers
- Input: S1_mme_48000_256 (folder), 19.6 s at 48000 Hz, channel 0 of 1, block size 256.
- Clicks: 8 (24.5 per minute). Dropouts: 1. Clipped runs: 0.
- DC offset 0.0004 (-69.1 dBFS). Noise floor -61.3 dBFS.
- Position in the block: 9 events, preferred offset 100.9 of 256, R=0.60, p=0.0349, clustered=no.
- Blocks: 3675 total, 0 late, 0 with status flags, 0 ADC-time gaps; 0 of 9 events near one (chance 0.0%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 103.6 | 0.000 | 1 | 19 | 107 |  | low |
| 02 | click | 104.4 | 0.000 | 25 | 19 | 147 |  | low |
| 03 | click | 102.6 | 0.000 | 3 | 19 | 59 |  | low |
| 04 | click | 103.0 | 0.000 | 2 | 19 | 80 |  | low |
| 05 | click | 105.6 | 0.000 | 13 | 19 | 203 |  | low |
| 06 | click | 104.0 | 0.000 | 3 | 19 | 129 |  | low |
| 07 | click | 18.2 | 0.000 | 1 | 3 | 107 |  | low |
| 08 | click | 1.8 | 0.000 | 3 | 0 | 85 |  | low |
| 09 | dropout_repeat | 14908.1 | 0.000 | 9 | 2795 | 69 |  | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 19600 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (9 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
