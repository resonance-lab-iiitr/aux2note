# crackle_core: how to use (T018)

`CODE/crackle_core.py` analyses a recording for crackle. Pure NumPy / SciPy, no GUI, no sound card.

```python
import crackle_core as cc
x, sr = cc.load_audio("capture.wav")
report = cc.analyze(x, sr, block_size=128,
                    blocks_table=None,          # per-block timing, see module docstring (T020 will record it)
                    meta={"source": "raw", "effects_off": True,
                          "monitoring_off": True, "silent_input": True},
                    raw=None)                   # raw sound-card capture, when x is the processed track
v = cc.verdict(report)
print(v["summary"])
for h in v["hypotheses"]:
    print(h["name"], h["confidence"], h["evidence"], h["next_test"])
```

Single detectors: `detect_clicks`, `detect_dropouts`, `detect_clipping`, `dc_and_noise_floor`,
`hum_peaks`, `block_alignment`, `correlate_with_blocks`, `ms_features` (one row per millisecond).
`example_output.txt` shows a verdict. Run the tests from `CODE/`:
`python3 -m unittest tests.test_phase10_crackle_core`.

Verdicts are hypotheses (software_scheduling, hardware_or_driver_input, software_dsp, gain_staging,
electrical, clean), never proof; the code judges numbers, not how a recording sounds.
