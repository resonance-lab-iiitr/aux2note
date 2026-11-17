"""
Find out WHERE the audio callback time goes (Live Looper Pro 2.0).
Save this file in the tools\\ folder, then run from the project folder:

    python tools\\profile_callback.py --block 128 --minutes 2
    python tools\\profile_callback.py --block 128 --minutes 2 --nogc

It needs no sound card and no cable. It runs the same scenario as soak_test
(4 takes, all effects, master bus) as fast as the PC can, and prints:
  1. cost per 10-second window  -> does the load CREEP UP over time?
  2. spikes (callbacks over 2x the median) and how far apart they are
  3. the functions that use the most time (cProfile)
Paste the whole output back.
"""
import argparse
import cProfile
import gc
import io
import os
import pstats
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from tools.soak_test import make_engine, Schedule  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, default=128)
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--minutes", type=float, default=2.0)
    ap.add_argument("--nogc", action="store_true", help="switch Python garbage collection off")
    a = ap.parse_args()
    if a.nogc:
        gc.disable()
    block, rate = a.block, a.rate
    bt = block / float(rate)
    eng, tracks = make_engine(rate, block, offline=True)
    sched = Schedule(eng, tracks)
    n = int(a.minutes * 60 * rate / block)
    rng = np.random.RandomState(1)
    ax = np.arange(block) / float(rate)
    out = np.zeros((block, 2), dtype=np.float32)
    times = np.zeros(n)
    print(f"block {block} = {bt * 1000:.2f} ms, {n} blocks, gc {'OFF' if a.nogc else 'on'}")
    tick = max(1, int(0.1 * rate / block))
    for b in range(n):
        if b % tick == 0:
            sched.tick(b * bt)
            eng.housekeeping()
        sig = (0.3 * np.sin(2 * np.pi * 220 * (ax + b * bt)) + 0.05 * rng.randn(block)).astype(np.float32)
        t0 = time.perf_counter()
        eng._callback(sig.reshape(-1, 1), out, block, None, None)
        times[b] = time.perf_counter() - t0

    print("\n1) COST PER 10 s OF AUDIO (does it creep up?)")
    per = int(10 / bt)
    for i in range(0, n, per):
        w = times[i:i + per]
        print(f"  {i * bt:6.0f} s  avg {1000 * w.mean():5.2f} ms  median {1000 * np.median(w):5.2f}  "
              f"max {1000 * w.max():6.2f}  late {int((w > bt).sum()):5d}")

    med = float(np.median(times))
    sp = np.where(times > 2 * med)[0]
    print(f"\n2) SPIKES (> 2x median {1000 * med:.2f} ms): {len(sp)} of {n}")
    if len(sp) > 3:
        gaps = np.diff(sp) * bt * 1000
        print(f"  gap between spikes: median {np.median(gaps):.0f} ms, "
              f"min {gaps.min():.0f} ms, max {gaps.max():.0f} ms")
        print("  first spike times (s):", ", ".join(f"{x * bt:.2f}" for x in sp[:10]))

    print("\n3) WHERE THE TIME GOES (20 s of audio, cProfile)")
    pr = cProfile.Profile()
    m = int(20 / bt)
    pr.enable()
    for b in range(m):
        eng._callback(sig.reshape(-1, 1), out, block, None, None)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12)
    print("\n".join(l for l in s.getvalue().splitlines() if l.strip())[:3500])


if __name__ == "__main__":
    main()
