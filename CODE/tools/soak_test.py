"""
Soak test for Live Looper Pro v2.0 (Phase 7).

Scenario (same in both modes):
  - record 4 tracks one after another (8 s each, overdubbing on the looping ones)
  - every effect on every track, plus the master bus, switched ON
  - keep everything playing until the chosen number of minutes is over

Two modes:

  python tools/soak_test.py --offline --minutes 10
      No sound card needed. Feeds the real audio callback with synthetic input
      as fast as possible and checks the callback time against the block time.
      This proves the CPU headroom. It cannot hear real dropouts.

  python tools/soak_test.py --live --minutes 10
      Uses your real sound card (WASAPI exclusive 48000/64, default devices).
      Play or make a little noise while it runs. At the end it prints the
      xrun counter from PortAudio. THIS is the real pass/fail for v2.0.

Options: --block 64  --rate 48000  --shared (live only)
Exit code 0 = PASS (0 xruns, 0 overruns), 1 = FAIL.
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

ALL5 = ("eq", "compressor", "distortion", "delay", "reverb")
# --fx scenarios: everything starts OFF, then only the listed effects are switched on.
FX_SETS = {
    "all":     {"track": lambda i: ALL5, "master": ALL5},
    # a realistic session: EQ + compressor on every track, reverb on track 1 only, master EQ
    "typical": {"track": lambda i: ("eq", "compressor") + (("reverb",) if i == 0 else ()), "master": ("eq",)},
    # no track effects at all: measures the engine itself (mixing, loops, telemetry)
    "none":    {"track": lambda i: (), "master": ()},
}

TAKE_SEC = 8.0
GAP_SEC = 1.0
N_TRACKS = 4


def make_engine(rate, block, offline, log=None, fx="all"):
    if offline:
        from tests import _stubs  # noqa: F401  (works without a sound card)
    from audio_engine import AudioEngine
    from track import Track
    eng = AudioEngine(sample_rate=rate, block_size=block, log=log or (lambda *a, **k: None))
    tracks = []
    for i in range(N_TRACKS):
        t = Track(f"Soak {i + 1}", rate)
        eng.add_track(t)
        tracks.append(t)
        for name in ALL5:                      # the track EQ is ON by default: start from all OFF
            getattr(t.effects, name).enabled = False
        for name in FX_SETS[fx]["track"](i):
            getattr(t.effects, name).enabled = True
    for chain in (eng.master_fx_l, eng.master_fx_r):
        for name in ALL5:
            getattr(chain, name).enabled = False
        for name in FX_SETS[fx]["master"]:
            getattr(chain, name).enabled = True
    eng.sync_master_fx()
    return eng, tracks


class Schedule:
    """Records the 4 takes at fixed times. call .tick(seconds_elapsed)."""

    def __init__(self, eng, tracks):
        self.eng, self.tracks = eng, tracks
        self.stage = 0   # 0..7 : even = start take k, odd = stop take k

    def tick(self, now):
        k = self.stage // 2
        if k >= N_TRACKS:
            return
        t_start = k * (TAKE_SEC + GAP_SEC)
        t_stop = t_start + TAKE_SEC
        if self.stage % 2 == 0 and now >= t_start:
            self.eng.arm_track(self.tracks[k], True)
            self.eng.rewind()
            self.eng.start_recording_armed()
            self.stage += 1
        elif self.stage % 2 == 1 and now >= t_stop:
            self.eng.stop_recording_armed()
            self.eng.arm_track(self.tracks[k], False)
            self.tracks[k].loop_enabled = True
            self.stage += 1

    @property
    def done(self):
        return self.stage >= N_TRACKS * 2


def verdict(eng, extra=None):
    s = eng.telemetry.summary()
    print("\n=== RESULT ===")
    for k in ("blocks", "block_ms", "avg_ms", "max_ms", "cpu_avg_pct", "cpu_peak_pct",
              "xruns", "overruns"):
        print(f"  {k:14s} {s[k]}")
    if extra:
        for k, v in extra.items():
            print(f"  {k:14s} {v}")
    ok = s["xruns"] == 0 and s["overruns"] == 0
    print("  VERDICT        " + ("PASS (0 xruns, 0 overruns)" if ok else "FAIL"))
    return 0 if ok else 1


def apply_tuning(args):
    """Optional experiments for the LIVE test (Windows parts are skipped elsewhere).
    --switch-interval S : Python thread switch interval in seconds (default is 0.005)
    --priority high     : raise this process to HIGH priority class
    --timer1            : ask Windows for a 1 ms system timer (timeBeginPeriod)"""
    applied = []
    if getattr(args, "switch_interval", None):
        sys.setswitchinterval(args.switch_interval)
        applied.append(f"switch-interval {args.switch_interval}")
    if os.name == "nt":
        import ctypes
        if getattr(args, "priority", None) == "high":
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.GetCurrentProcess.restype = wintypes.HANDLE
            k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k.SetPriorityClass.restype = wintypes.BOOL
            ok = k.SetPriorityClass(k.GetCurrentProcess(), 0x00000080)
            applied.append("priority HIGH" + ("" if ok else " (FAILED)"))
        if getattr(args, "timer1", False):
            ctypes.windll.winmm.timeBeginPeriod(1)
            applied.append("timer 1 ms")
    elif getattr(args, "priority", None) or getattr(args, "timer1", False):
        applied.append("(priority/timer options only work on Windows)")
    return applied


def run_offline(args):
    eng, tracks = make_engine(args.rate, args.block, offline=True, fx=args.fx)
    sched = Schedule(eng, tracks)
    block, rate = args.block, args.rate
    n_blocks = int(args.minutes * 60 * rate / block)
    rng = np.random.RandomState(1)
    t_axis = np.arange(block) / float(rate)
    outdata = np.zeros((block, 2), dtype=np.float32)
    times = np.zeros(n_blocks, dtype=np.float32)
    print(f"OFFLINE soak: {args.minutes} min of audio = {n_blocks} blocks of {block} "
          f"({1000.0 * block / rate:.2f} ms each) ...")
    wall0 = time.perf_counter()
    tick_every = max(1, int(0.1 * rate / block))
    for b in range(n_blocks):
        if b % tick_every == 0:
            sched.tick(b * block / float(rate))
            eng.housekeeping()
        ph = b * block / float(rate)
        sig = 0.3 * np.sin(2 * np.pi * 220.0 * (t_axis + ph)) + 0.05 * rng.randn(block)
        indata = sig.astype(np.float32).reshape(-1, 1)
        t0 = time.perf_counter()
        eng._callback(indata, outdata, block, None, None)
        times[b] = time.perf_counter() - t0
        if not np.isfinite(outdata).all():
            print("FAIL: NaN/inf in output at block", b)
            return 1
        if b and b % (n_blocks // 10 or 1) == 0:
            print(f"  {100 * b // n_blocks:3d}%  worst so far {1000 * times[:b].max():.2f} ms")
    wall = time.perf_counter() - wall0
    bt = block / float(rate)
    extra = {
        "p99_ms": round(1000 * float(np.percentile(times, 99)), 3),
        "over_70pct": int((times > 0.7 * bt).sum()),
        "takes_done": sched.done,
        "speed": f"{args.minutes * 60 / wall:.1f}x real time",
    }
    return verdict(eng, extra)


def run_live(args):
    from audio_engine import AudioEngine  # noqa: F401
    import sounddevice as sd
    from stream_config import StreamConfig, WASAPI_NAME
    eng, tracks = make_engine(args.rate, args.block, offline=False,
                              log=lambda msg, level=None: print(msg), fx=args.fx)
    in_dev = out_dev = None
    for api in sd.query_hostapis():
        if api["name"] == WASAPI_NAME:
            in_dev, out_dev = api["default_input_device"], api["default_output_device"]
    if in_dev is None or in_dev < 0 or out_dev < 0:
        print("No WASAPI default devices found. Use the app (AUTO + MOUNT) to check your devices.")
        return 1
    cfg = StreamConfig(exclusive=not args.shared, sample_rate=args.rate, block_size=args.block)
    try:
        step = eng.open_stream(in_dev, out_dev, cfg)
    except RuntimeError as e:
        print("FAIL: could not open the stream:", e)
        return 1
    print(f"LIVE soak running in {eng.mode_name} for {args.minutes} min. "
          "Make some noise near the mic / play your instrument. Ctrl+C stops early.")
    tuning = apply_tuning(args)
    print("Tuning:", ", ".join(tuning) if tuning else "none (baseline)")
    sched = Schedule(eng, tracks)
    t0 = time.time()
    last_print = 0
    try:
        eng.play()
        while time.time() - t0 < args.minutes * 60:
            now = time.time() - t0
            sched.tick(now)
            eng.housekeeping()
            if now - last_print >= 15:
                last_print = now
                print(f"  {now / 60:5.1f} min | {eng.telemetry.summary()['cpu_avg_pct']}% CPU | "
                      f"xruns {eng.telemetry.xruns} | overruns {eng.telemetry.overruns}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("stopped early")
    finally:
        eng.stop()
        rc = verdict(eng, {"mode": eng.mode_name, "takes_done": sched.done,
                           "tuning": ", ".join(tuning) if tuning else "none",
                           "fx": args.fx})
        eng.close_stream()
    return rc


def main():
    ap = argparse.ArgumentParser(description="Live Looper Pro soak test")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--offline", action="store_true", help="no sound card (default)")
    g.add_argument("--live", action="store_true", help="real sound card")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--block", type=int, default=64)
    ap.add_argument("--rate", type=int, default=48000)
    ap.add_argument("--fx", choices=sorted(FX_SETS), default="all",
                    help="which effects are on: all (default), typical, none")
    ap.add_argument("--shared", action="store_true", help="live: shared mode instead of exclusive")
    ap.add_argument("--switch-interval", type=float, default=None, dest="switch_interval",
                    help="live: Python thread switch interval in s (try 0.0005)")
    ap.add_argument("--priority", choices=["high"], default=None, help="live, Windows: process priority")
    ap.add_argument("--timer1", action="store_true", help="live, Windows: 1 ms system timer")
    args = ap.parse_args()
    sys.exit(run_live(args) if args.live else run_offline(args))


if __name__ == "__main__":
    main()
