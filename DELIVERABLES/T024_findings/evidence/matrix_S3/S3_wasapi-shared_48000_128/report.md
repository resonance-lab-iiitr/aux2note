# Verdict: hardware_or_driver_input (confidence medium)

Most likely: hardware_or_driver_input (confidence medium). 3 click(s), 9.0 per minute, at random positions inside the block (no fixed offset).

## Evidence
- 3 click(s), 9.0 per minute, at random positions inside the block (no fixed offset).
- The capture was made with nothing playing / effects and monitoring off, so the clicks were not produced by the program's own sound.
- The clicks are present in the raw sound-card capture, before any DSP.
- Note: 0 late block(s), 0 with PortAudio status flags, 233 ADC-time gap(s) in 7530 blocks.

## Next test
Record 60 s of the RAW input with effects and monitoring off and nothing playing, then repeat with another USB port / cable and in another driver (WASAPI exclusive, ASIO). Clicks at the same rate in every engine mode point at the interface or its driver.

## Other hypotheses
- electrical (medium): 50 Hz hum with 4 distinct harmonic(s), strongest -89.0 dBFS.

## Numbers
- Input: S3_wasapi-shared_48000_128 (folder), 20.1 s at 48000 Hz, channel 0 of 1, block size 128.
- Clicks: 3 (9.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0000 (-105.6 dBFS). Noise floor -21.0 dBFS (no quiet parts, not meaningful).
- Hum: 50 Hz, 4 distinct harmonic(s), strongest -89.0 dBFS.
- Position in the block: 3 events, preferred offset 73.0 of 128, R=0.77, p=0.1723, clustered=no.
- Blocks: 7530 total, 0 late, 0 with status flags, 233 ADC-time gaps; 0 of 3 events near one (chance 9.3%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 28.4 | 0.041 | 8 | 10 | 81 | 120.979 | high |
| 02 | click | 75.8 | 0.145 | 10 | 28 | 52 | 73.583 | high |
| 03 | click | 65.7 | 0.080 | 7 | 24 | 83 | 83.604 | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 20080 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (3 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
