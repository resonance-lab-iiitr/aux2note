# Verdict: hardware_or_driver_input (confidence high)

Most likely: hardware_or_driver_input (confidence high). 2003 click(s), 6009.0 per minute, at random positions inside the block (no fixed offset).

## Evidence
- 2003 click(s), 6009.0 per minute, at random positions inside the block (no fixed offset).
- The capture was made with nothing playing / effects and monitoring off, so the clicks were not produced by the program's own sound.
- No late block, status flag or ADC-time gap in 3750 blocks.
- The clicks are present in the raw sound-card capture, before any DSP.

## Next test
Record 60 s of the RAW input with effects and monitoring off and nothing playing, then repeat with another USB port / cable and in another driver (WASAPI exclusive, ASIO). Clicks at the same rate in every engine mode point at the interface or its driver.

## Numbers
- Input: 20261112_144415_excl256 (folder), 20.0 s at 48000 Hz, channel 0 of 1, block size 256.
- Clicks: 2003 (6009.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0000 (-105.1 dBFS). Noise floor -21.0 dBFS (no quiet parts, not meaningful).
- Position in the block: 2003 events, preferred offset 125.1 of 256, R=0.05, p=0.0062, clustered=no.
- Blocks: 3750 total, 0 late, 0 with status flags, 0 ADC-time gaps; 0 of 2003 events near one (chance 0.0%, p=1.0000).

## Worst events (full list in events.csv)
| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |
|---|---|---|---|---|---|---|---|---|
| 01 | click | 2709.4 | 0.162 | 19 | 508 | 5 |  | high |
| 02 | click | 5652.5 | 0.173 | 17 | 1059 | 214 |  | high |
| 03 | click | 1683.4 | 0.162 | 19 | 315 | 165 |  | high |
| 04 | click | 14253.4 | 0.144 | 21 | 2672 | 132 |  | high |
| 05 | click | 12477.5 | 0.177 | 21 | 2339 | 134 |  | high |
| 06 | click | 16701.4 | 0.144 | 21 | 3131 | 132 |  | high |
| 07 | click | 17151.5 | 0.177 | 21 | 3215 | 230 |  | high |
| 08 | click | 6657.5 | 0.173 | 17 | 1248 | 70 |  | high |
| 09 | click | 1767.4 | 0.142 | 21 | 331 | 100 |  | high |
| 10 | click | 3645.4 | 0.162 | 19 | 683 | 133 |  | high |

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 20000 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): ok.
- excerpts/event_NN.wav: +/- 1 s around the worst events (10 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
