"""T031: read a logs/split_timing_*.csv and print what the two streams really did.

    python tools/split_replay.py logs/split_timing_XXXX.csv [block]

Prints per stream: callbacks per second, burst structure, frames per second (input callbacks are
assumed to carry `block` frames each), and a replay of the ring buffer for prefill 1-5 so you can
see how many underflows / trims each prefill would give on that exact trace. No audio hardware needed.
"""
import csv
import sys

import numpy as np


def load(path):
    rows = list(csv.DictReader(open(path, newline="")))
    t = np.array([float(r["t_ms"]) for r in rows])
    kind = np.array([r["kind"] for r in rows])
    return t, kind


def bursts(t, gap_ms=2.0):
    parts = np.split(t, np.where(np.diff(t) > gap_ms)[0] + 1)
    return np.array([len(p) for p in parts]), np.array([p[0] for p in parts])


def replay(t, kind, block, prefill, trim_blocks=4, ring_blocks=16):
    cap, w, r, primed, under, trims, over, n = ring_blocks * block, 0, 0, False, 0, 0, 0, 0
    for k in kind:
        if k == "in":
            if w - r + block > cap:
                over += 1
                continue
            w += block
            continue
        fill = w - r
        if not primed:
            if fill < prefill * block:
                continue
            primed = True
        n += 1
        if fill > prefill * block + trim_blocks * block:
            r, fill, trims = w - prefill * block, prefill * block, trims + 1
        if fill >= block:
            r += block
        else:
            under += 1
    return n, under, trims, over


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    block = int(argv[1]) if len(argv) > 1 else 160
    t, kind = load(argv[0])
    for k in ("in", "out"):
        tk = t[kind == k]
        if len(tk) < 3:
            continue
        sz, st = bursts(tk)
        dur = (tk[-1] - tk[0]) / 1000.0
        print("%-3s %6d callbacks, %.1f /s, %.0f frames/s (if each = %d), burst period %.2f ms, "
              "blocks per burst avg %.2f" % (k, len(tk), len(tk) / dur, len(tk) / dur * block, block,
                                             float(np.diff(st).mean()), float(sz.mean())))
    print("expected frames/s for a real-time stream is the sample rate (e.g. 48000)")
    for p in (1, 2, 3, 4, 5):
        n, u, tr, ov = replay(t, kind, block, p)
        print("replay prefill %d: output blocks %d, underflow %.1f %%, trims %d, overflows %d"
              % (p, n, 100.0 * u / max(1, n), tr, ov))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
