"""
Generate / check golden DSP reference output.

    python tools/golden.py          # (re)write tests/golden/baseline_dsp.npz
    python tools/golden.py --check  # compare and print max error per case

Only regenerate on UNCHANGED effects. After Phase 3 it is the reference
that proves the faster code sounds the same.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np
from effects import EffectsChain

SR = 48000
BLOCK = 64
SECONDS = 0.8
OUT = os.path.join(ROOT, "tests", "golden", "baseline_dsp.npz")


def _input():
    rs = np.random.RandomState(42)
    n = int(SR * SECONDS)
    t = np.arange(n) / SR
    burst = np.zeros(n)
    burst[: SR // 10] = 0.5 * np.sin(2 * np.pi * 330 * t[: SR // 10])
    return (burst + 0.05 * rs.randn(n)).astype(np.float32)


def _chain(case):
    c = EffectsChain(SR)
    if case in ("delay", "all_fx"):
        c.delay.enabled = True
        c.delay.time_sec, c.delay.feedback, c.delay.mix = 0.2, 0.4, 0.4
    if case in ("reverb", "all_fx"):
        c.reverb.enabled = True
        c.reverb.room_size, c.reverb.damping, c.reverb.mix = 0.7, 0.3, 0.35
    if case in ("compressor", "all_fx"):
        c.compressor.enabled = True
        c.compressor.threshold_db, c.compressor.ratio = -24.0, 4.0
    if case == "all_fx":
        c.distortion.enabled = True
        c.distortion.drive, c.distortion.mix = 0.3, 0.5
        c.eq.bands[2].set_gain(4.0)
    return c


CASES = ["delay", "reverb", "compressor", "all_fx"]


def render_case(case):
    x = _input()
    c = _chain(case)
    out = [c.process(x[i:i + BLOCK].copy()) for i in range(0, len(x) - BLOCK + 1, BLOCK)]
    return np.concatenate(out).astype(np.float32)


def main():
    if "--check" in sys.argv:
        ref = np.load(OUT)
        for k in CASES:
            print(f"{k:12s} max error {float(np.max(np.abs(render_case(k) - ref[k]))):.3e}")
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, **{k: render_case(k) for k in CASES})
    print("wrote", OUT, f"({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
