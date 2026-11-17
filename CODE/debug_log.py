"""
debug_log.py  (Live Looper Pro v2.0, Phase 6)

Pure Python (no Tk, no sound card): ring buffer + rotating log file, a
real-time-safe event counter for the audio callback, the copyable debug
report, the global exception handler and the F12 test-signal generator.
"""
import collections
import logging
import logging.handlers
import os
import platform
import queue
import sys
import threading
import time
import traceback

import numpy as np

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRIT")
_RANK = {n: i for i, n in enumerate(LEVELS)}
RING_SIZE = 2000
_PREFIX_LEVEL = {"BOOT": "DEBUG", "PROBE": "DEBUG", "WARN": "WARN",
                 "ERROR": "ERROR", "CRIT": "CRIT"}
from version import APP_VERSION as VERSION  # noqa: E402


def level_for(prefix):
    """Old code logs with a 'prefix' (SYS, AUDIO, ERROR ...): map to a level."""
    return _PREFIX_LEVEL.get(str(prefix).upper(), "INFO")


def default_log_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


class DebugLog:
    """Thread-safe. add() may be called from any thread EXCEPT the audio
    callback (use log_rt() there)."""

    def __init__(self, log_dir=None, ring_size=RING_SIZE, to_file=True):
        self.ring = collections.deque(maxlen=ring_size)   # (ts, level, text)
        self.pending = queue.Queue()                      # new records for the GUI
        self._lock = threading.Lock()
        self.log_dir = log_dir or default_log_dir()
        self._file = None
        self._rt = {}                                     # name -> count (audio thread)
        self._rt_seen = {}
        if to_file:
            try:
                os.makedirs(self.log_dir, exist_ok=True)
                h = logging.handlers.RotatingFileHandler(
                    os.path.join(self.log_dir, "looper.log"), maxBytes=500_000,
                    backupCount=3, encoding="utf-8")
                h.setFormatter(logging.Formatter("%(message)s"))
                lg = logging.getLogger("looper.%d" % id(self))
                lg.setLevel(logging.DEBUG)
                lg.propagate = False
                lg.addHandler(h)
                self._file, self._handler = lg, h
            except Exception:
                self._file = None      # logging must never stop the app

    # ---- normal logging ------------------------------------------------ #
    def add(self, text, prefix="INFO"):
        level = level_for(prefix)
        if str(prefix).upper() in _RANK and str(prefix).upper() not in _PREFIX_LEVEL:
            level = str(prefix).upper()
        rec = (time.time(), level, f"[{prefix}] {text}")
        with self._lock:
            self.ring.append(rec)
            if self._file is not None:
                try:
                    self._file.info(format_record(rec))
                except Exception:
                    pass
        self.pending.put(rec)
        return rec

    def records(self, min_level="DEBUG", search=""):
        return filter_records(list(self.ring), min_level, search)

    def last_lines(self, n=100):
        return [format_record(r) for r in list(self.ring)[-n:]]

    def close(self):
        if self._file is not None:
            try:
                self._handler.close()
                self._file.removeHandler(self._handler)
            except Exception:
                pass
            self._file = None

    # ---- real-time safe ------------------------------------------------ #
    def log_rt(self, name):
        """For the audio callback: only bumps a counter (no text, no lock)."""
        self._rt[name] = self._rt.get(name, 0) + 1

    def drain_rt(self):
        """GUI thread: turn counter growth into at most one line per event name."""
        out = []
        for name, n in list(self._rt.items()):
            new = n - self._rt_seen.get(name, 0)
            if new > 0:
                self._rt_seen[name] = n
                out.append(self.add(f"{name} x{new} (audio thread, total {n})", "AUDIO"))
        return out


def format_record(rec):
    ts, level, text = rec
    return f"{time.strftime('%H:%M:%S', time.localtime(ts))} {level:<5} {text}"


def filter_records(recs, min_level="DEBUG", search=""):
    rank = _RANK.get(min_level, 0)
    s = (search or "").strip().lower()
    return [r for r in recs if _RANK.get(r[1], 0) >= rank and (not s or s in r[2].lower())]


# ---------------------------------------------------------------------- #
# Engine / tracks snapshots (used by the Debug Center tabs and the report)
# ---------------------------------------------------------------------- #
def split_text(engine, long=False):
    """'-' unless the engine runs a split in/out stream; else its hand-off counters."""
    f = getattr(engine, "split_stats", None)
    st = f() if f else None
    if not st:
        return "-"
    if long:
        return (f"prefill {st['prefill_blocks']} block(s), ring {st['ring_blocks']}, underflows {st['underflows']} "
                f"(silent blocks), overflows {st['overflows']}, trims {st['trims']}, "
                f"output blocks {st['out_blocks']}")
    return f"{st['underflows']} underflows, {st['trims']} trims, prefill {st['prefill_blocks']}"


def engine_snapshot(engine):
    tel = engine.telemetry
    s = tel.summary()
    cfg = engine.active_config
    rows = [
        ("state", "MOUNTED" if engine.is_active else "IDLE"),
        ("transport", "PLAYING" if engine.is_playing else "STOPPED"),
        ("mode", engine.mode_name),
        ("config", str(cfg) if cfg is not None else "-"),
        ("sample rate / block", f"{engine.sample_rate} Hz / {engine.block_size}"),
        ("reported latency (ms)", _f(_safe(engine.latency_ms))),
        ("measured RTT (ms)", _f(engine.measured_rtt_ms())),
        ("record offset (samples)", engine.record_latency_samples),
        ("CPU (ours)", f"{s['cpu_avg_pct']} % (peak {s['cpu_peak_pct']} %)"),
        ("CPU (PortAudio)", _f(engine.pa_cpu_load(), 100, " %")),
        ("xruns / overruns", f"{tel.xruns} / {tel.overruns}"),
        ("split stream", split_text(engine, long=True)),
        ("blocks processed", s["blocks"]),
        ("tracks", len(engine.tracks)),
        ("playhead (s)", f"{engine.playhead / float(engine.sample_rate):.2f}"),
        ("peak L / R / in", f"{engine.peak_l:.2f} / {engine.peak_r:.2f} / {engine.input_peak:.2f}"),
        ("test signal", getattr(engine, "test_signal_name", None) or "off"),
        ("log queue (GUI)", "-"),
    ]
    return rows


def tracks_snapshot(engine, cost_pct=None):
    """One row per track: name, length s, offset ms, enabled effects, est. CPU %."""
    out = []
    for t in engine.tracks:
        fx = [n for n in ("eq", "compressor", "distortion", "delay", "reverb")
              if getattr(getattr(t.effects, n, None), "enabled", False)]
        est = None
        if cost_pct:
            est = sum(cost_pct.get(n, 0.0) for n in fx)
        out.append((t.name, round(t.length / float(t.sample_rate), 2),
                    round(t.offset * 1000.0 / t.sample_rate, 1),
                    ", ".join(fx) or "none", None if est is None else round(est, 1)))
    return out


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _f(v, mul=1.0, unit=""):
    return "-" if v is None else f"{v * mul:.1f}{unit}"


# ---------------------------------------------------------------------- #
# Debug report
# ---------------------------------------------------------------------- #
def library_versions():
    out = {}
    for name in ("numpy", "scipy", "sounddevice", "soundfile", "lameenc"):
        try:
            m = __import__(name)
            out[name] = getattr(m, "__version__", "installed")
        except Exception:
            out[name] = "not installed"
    return out


def build_report(engine, settings=None, dlog=None, n_log=100, device_rows=None):
    L = [f"LIVE LOOPER PRO {VERSION} DEBUG REPORT  {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    L.append("== VERSIONS ==")
    L.append(f"OS: {platform.platform()}")
    L.append(f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})")
    for k, v in library_versions().items():
        L.append(f"{k}: {v}")
    try:
        import power_plan
        L.append(f"Power plan: {power_plan.describe(power_plan.get_active_scheme())}")
    except Exception:
        L.append("Power plan: unknown")
    L += ["", "== SETTINGS =="]
    for k, v in sorted((settings or {}).items()):
        L.append(f"{k}: {v}")
    L += ["", "== ENGINE =="]
    for k, v in engine_snapshot(engine):
        L.append(f"{k}: {v}")
    L += ["", "== TELEMETRY =="]
    for k, v in engine.telemetry.summary().items():
        L.append(f"{k}: {v}")
    L += ["", "== CALIBRATION =="]
    c = engine.calibration
    L.append("none" if not c else f"RTT {c['rtt_ms']:.2f} ms for {c['key']} "
             f"({c['rtt_samples']} samples)")
    if device_rows:
        L += ["", "== DEVICES =="]
        for r in device_rows:
            L.append(f"ID {r['id']} | {r['driver']} | in {r['max_in']} out {r['max_out']} | {r['name']}")
    L += ["", f"== LAST {n_log} LOG LINES =="]
    L += dlog.last_lines(n_log) if dlog else []
    return "\n".join(L) + "\n"


def save_report(text, log_dir=None):
    d = log_dir or default_log_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, time.strftime("report_%Y%m%d_%H%M%S.txt"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ---------------------------------------------------------------------- #
# Global exception handling
# ---------------------------------------------------------------------- #
def handle_exception(dlog, exc_type, exc, tb, where="", notify=None):
    """Write the traceback to the log; never raises."""
    try:
        txt = "".join(traceback.format_exception(exc_type, exc, tb))
        dlog.add(f"Unexpected error{' in ' + where if where else ''}: {exc}", "CRIT")
        for line in txt.rstrip().splitlines():
            dlog.add(line, "DEBUG")
        if notify:
            notify("Something went wrong",
                   f"{exc_type.__name__}: {exc}\n\nThe app is still running. Press "
                   "COPY DEBUG REPORT and paste it to Claude.")
    except Exception:
        pass


def install_exception_hooks(dlog, root=None, notify=None):
    def hook(t, v, tb):
        handle_exception(dlog, t, v, tb, "main thread", notify)

    def thread_hook(args):
        handle_exception(dlog, args.exc_type, args.exc_value, args.exc_traceback,
                         f"thread {getattr(args.thread, 'name', '?')}", notify)
    sys.excepthook = hook
    threading.excepthook = thread_hook
    if root is not None:
        root.report_callback_exception = lambda t, v, tb: handle_exception(
            dlog, t, v, tb, "GUI callback", notify)


# ---------------------------------------------------------------------- #
# F12 test signal (plays instead of the looper mix, like calibration)
# ---------------------------------------------------------------------- #
class TestSignal:
    """kind: 'sine' or 'noise'. process() fills outdata, no big allocations."""
    __test__ = False        # not a pytest/unittest case

    def __init__(self, kind, sample_rate, level=0.1, freq=440.0):
        self.kind = kind
        self.sr = float(sample_rate)
        self.level = float(min(max(level, 0.0), 0.5))
        self.freq = freq
        self.phase = 0
        self._rng = np.random.default_rng(1)

    def process(self, outdata, frames):
        if self.kind == "noise":
            x = (self.level * (self._rng.random(frames) * 2.0 - 1.0)).astype(np.float32)
        else:
            n = np.arange(self.phase, self.phase + frames)
            x = (self.level * np.sin(2.0 * np.pi * self.freq * n / self.sr)).astype(np.float32)
            self.phase = (self.phase + frames) % int(self.sr)   # 1 s period keeps numbers small
        outdata[:, 0] = x
        if outdata.shape[1] > 1:
            outdata[:, 1] = x
        return float(np.max(np.abs(x))) if frames else 0.0
