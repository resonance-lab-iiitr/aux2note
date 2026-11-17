"""
Per-effect CPU cost, as a percent of the audio block time.

    python tools/dsp_bench.py            # block 64 @ 48000
    python tools/dsp_bench.py 128 44100  # block 128 @ 44100

Also used by the FX dialog ("CPU cost" labels) through effects.benchmark_costs().
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from effects import benchmark_costs  # noqa: E402

TARGET = 20.0   # percent per chain at block 64 (Phase 3 goal)


def main():
    block = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    sr = int(sys.argv[2]) if len(sys.argv) > 2 else 48000
    costs = benchmark_costs(sr, block)
    print(f"block {block} @ {sr} Hz = {1000.0 * block / sr:.3f} ms per block")
    for name, pct in costs.items():
        print(f"  {name:12s} {pct:6.1f} %")
    ok = costs["ALL (chain)"] < TARGET
    print(f"chain target < {TARGET:.0f}%: {'PASS' if ok else 'MISSED'}")


if __name__ == "__main__":
    main()
