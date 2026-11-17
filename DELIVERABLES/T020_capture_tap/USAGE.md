# T020 raw capture tap: how to use it

What it does: records exactly what the sound card hands to the audio callback (all input channels, float32,
BEFORE CLEAN INPUT and any effect) plus the timing of every block. Recorded tracks hold the cleaned signal, so this
is the only way to see the real hardware signal (D021).

## From code (the Lab tab in T021 will wrap this)
```python
rec = engine.start_capture(max_seconds=120, capture_output=False)   # allocates everything now, off the audio thread
# ... play / record / run a test signal as usual ...
rec = engine.stop_capture()            # detaches; rec.full is True if the buffer filled up first
rec.to_files("captures/mytest")        # raw.wav, blocks.csv.gz, meta.json (+ output.wav if capture_output=True)
```
Works in every callback branch: normal mix, F12 test signal and calibration. With no capture running the callback does the
same work as before (one `is None` check).

## Files written by `to_files(folder)`
- `raw.wav`: float32, all input channels, same samples the card delivered.
- `blocks.csv.gz`: one row per callback. Columns: `index, start, frames, cb_ms, status, adc_time, adc_err_ms, current_time, output_time, t_start`.
  `start` = first sample of the block in raw.wav; `status` bits 1 input underflow, 2 input overflow, 4 output underflow, 8 output overflow;
  `adc_err_ms` = (ADC time step) - (previous frames / rate), 0 for a perfect clock, empty/nan when PortAudio gave no time.
  `start frames cb_ms status adc_time` are the names crackle_core reads (D045).
- `meta.json`: sample rate, block size, channels, frames, blocks, `full`, number of blocks with a status flag.

## Limits
Default 120 s (about 23 MB per input channel at 48 kHz). When the buffer is full the tap stops by itself (`full`: true); it never grows.
Not yet in the GUI: T021 adds the Lab tab. Not yet tested on a real sound card (sandbox has none); the cffi `time_info` fields are read with `getattr`
and fall back to nan if absent.
