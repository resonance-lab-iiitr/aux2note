# Verdict: electrical (confidence high)

Most likely: electrical (confidence high). DC offset 0.0200 (-34.0 dBFS).

## Evidence
- DC offset 0.0200 (-34.0 dBFS).

## Next test
Run the interface from a different USB port or a powered hub, unplug other devices (laptop charger, monitors), use balanced cables, and record 30 s of silence again. Note whether the hum level or the DC offset changes.

## Numbers
- Input: sample_dc_and_hum.wav (file), 5.0 s at 48000 Hz, channel 0 of 1, block size 128.
- Clicks: 0 (0.0 per minute). Dropouts: 0. Clipped runs: 0.
- DC offset 0.0200 (-34.0 dBFS). Noise floor -17.0 dBFS (no quiet parts, not meaningful).

## Files
- events.csv: every event (type, start_sample, t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block, nearest_engine_event_ms, confidence).
- ms.csv.gz: 5000 rows, one per 1 ms of audio (column list in crackle_report.py docstring).
- report.png and event_NN.png (the worst 10 events, +/- 20 ms): skipped.
- excerpts/event_NN.wav: +/- 1 s around the worst events (0 kept).
- analysis_pack.zip: everything above, limit 20.0 MB.

## Limits
- No blocks.csv.gz: correlation with late blocks, status flags and ADC-time gaps was not possible, so a scheduling cause cannot be ruled in or out by timing.
- Pictures: skipped (--no-png).
- Judged from numbers (samples, spectra, timing), not from listening. These are hypotheses, not proof.
