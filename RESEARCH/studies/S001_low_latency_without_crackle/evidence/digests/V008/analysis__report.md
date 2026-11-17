# Verdict: hardware_or_driver_input (confidence medium)

Most likely: hardware_or_driver_input (confidence medium). 2932 click(s), 8796.0 per minute, at random positions inside the block (no fixed offset).

## Evidence
- 2932 click(s), 8796.0 per minute, at random positions inside the block (no fixed offset).
- The capture was made with nothing playing / effects and monitoring off, so the clicks were not produced by the program's own sound.
- The clicks are present in the raw sound-card capture, before any DSP.
- Note: 0 late block(s), 0 with PortAudio status flags, 5 ADC-time gap(s) in 7500 blocks.

## Next test
Record 60 s of the RAW input with effects and monitoring off and nothing playing, then repeat with another USB port / cable and in another driver (WASAPI exclusive, ASIO). Clicks at the same rate in every engine mode point at the interface or its driver.

## Numbers
- Input: S3_wasapi-excl_48000_128 (folder), 20.0 s at 48000 Hz, channel 0 of 1, block size 128.
- Clicks: 2932 (8796.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0000 (-103.9 dBFS). Noise floor -21.1 dBFS (no quiet parts, not meaningful).
- Position in the block: 2932 events, preferred offset 105.6 of 128, R=0.07, p=0.0000, clustered=no.
- Blocks: 7500 total, 0 late, 0 with status flags, 5 ADC-time gaps; 0 of 2932 events near one (chance 0.2%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 19177.6 | 0.230 | 14 | 7191 | 75 | 1110.896 | high |
| 02 | click | 8638.6 | 0.116 | 14 | 3239 | 61 | 345.396 | high |
| 03 | click | 14422.6 | 0.142 | 14 | 5408 | 61 | 340.062 | high |
| 04 | click | 8620.6 | 0.116 | 14 | 3232 | 93 | 363.396 | high |
| 05 | click | 9388.6 | 0.142 | 14 | 3520 | 93 | 404.604 | high |
| 06 | click | 8977.6 | 0.142 | 14 | 3366 | 77 | 6.396 | high |
| 07 | click | 16639.6 | 0.162 | 15 | 6239 | 109 | 1427.062 | high |
| 08 | click | 17431.6 | 0.142 | 14 | 6536 | 109 | 635.062 | high |
| 09 | click | 9619.6 | 0.142 | 14 | 3607 | 45 | 635.604 | high |
| 10 | click | 8596.6 | 0.120 | 14 | 3223 | 93 | 387.396 | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 20000 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (10 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
