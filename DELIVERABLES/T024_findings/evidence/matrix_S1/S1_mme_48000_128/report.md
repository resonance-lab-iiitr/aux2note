# Verdict: hardware_or_driver_input (confidence medium)

Most likely: hardware_or_driver_input (confidence medium). 8 click(s), 24.5 per minute, at random positions inside the block (no fixed offset).

## Evidence
- 8 click(s), 24.5 per minute, at random positions inside the block (no fixed offset).
- The capture was made with nothing playing / effects and monitoring off, so the clicks were not produced by the program's own sound.
- The clicks are present in the raw sound-card capture, before any DSP.
- Note: 1 late block(s), 0 with PortAudio status flags, 0 ADC-time gap(s) in 7350 blocks.

## Next test
Record 60 s of the RAW input with effects and monitoring off and nothing playing, then repeat with another USB port / cable and in another driver (WASAPI exclusive, ASIO). Clicks at the same rate in every engine mode point at the interface or its driver.

## Numbers
- Input: S1_mme_48000_128 (folder), 19.6 s at 48000 Hz, channel 0 of 1, block size 128.
- Clicks: 8 (24.5 per minute). Dropouts: 4. Clipped runs: 0.
- DC offset 0.0004 (-69.1 dBFS). Noise floor -62.5 dBFS.
- Position in the block: 12 events, preferred offset 79.0 of 128, R=0.12, p=0.8404, clustered=no.
- Blocks: 7350 total, 1 late, 0 with status flags, 0 ADC-time gaps; 1 of 12 events near one (chance 0.0%, p=0.0033).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 103.6 | 0.000 | 1 | 38 | 107 | 103.562 | low |
| 02 | click | 104.4 | 0.000 | 25 | 39 | 19 | 104.396 | low |
| 03 | click | 102.6 | 0.000 | 3 | 38 | 59 | 102.562 | low |
| 04 | click | 103.0 | 0.000 | 2 | 38 | 80 | 103.0 | low |
| 05 | click | 105.6 | 0.000 | 13 | 39 | 75 | 105.562 | low |
| 06 | click | 104.0 | 0.000 | 3 | 39 | 1 | 104.021 | low |
| 07 | click | 18.2 | 0.000 | 1 | 6 | 107 | 18.229 | low |
| 08 | click | 1.8 | 0.000 | 3 | 0 | 85 | 1.771 | low |
| 09 | dropout_repeat | 4009.0 | 0.000 | 9 | 1503 | 50 | 4009.042 | high |
| 10 | dropout_repeat | 11200.6 | 0.002 | 9 | 4200 | 31 | 11200.646 | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 19600 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (10 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
