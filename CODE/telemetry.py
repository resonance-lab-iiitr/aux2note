"""
telemetry.py  (Live Looper Pro v2.0, Phase 4a)

Lock-free counters for the audio callback. The callback calls `record()` once
per block (a few float operations, no allocation, no logging, no lock). The
GUI thread only READS the plain attributes. A torn read can at worst show a
number that is one block old, which is harmless.

CPU load = time spent inside the callback / time the block lasts.
    block 64 @ 48000 Hz lasts 1.333 ms. If the callback needs 0.4 ms -> 30 %.
Above 100 % the sound card runs out of data (an "xrun", heard as a crackle).
"""

import numpy as np

HISTORY = 100          # blocks kept for the load graph
EMA_ALPHA = 0.05       # smoothing of the average (about the last 20 blocks)
WARN_LOAD = 0.70       # graph and status turn red above this


class Telemetry:
    def __init__(self, history=HISTORY):
        self.history_len = history
        self.reset()

    def reset(self):
        self.history = np.zeros(self.history_len, dtype=np.float64)  # seconds per block
        self._idx = 0
        self.blocks = 0
        self.last_s = 0.0
        self.avg_s = 0.0
        self.max_s = 0.0
        self.block_s = 0.0           # duration of one block (seconds)
        self.xruns = 0               # blocks where PortAudio reported a problem
        self.overruns = 0            # callback took longer than the block itself
        self.input_underflow = 0
        self.input_overflow = 0
        self.output_underflow = 0
        self.output_overflow = 0

    # ---- called from the audio thread --------------------------------- #
    def record(self, start, end, frames, sample_rate, status=None):
        dt = end - start
        if dt < 0.0:
            dt = 0.0
        block_s = frames / float(sample_rate) if sample_rate else 0.0
        self.block_s = block_s
        self.last_s = dt
        if self.blocks == 0:
            self.avg_s = dt
        else:
            self.avg_s += EMA_ALPHA * (dt - self.avg_s)
        if dt > self.max_s:
            self.max_s = dt
        self.history[self._idx] = dt
        self._idx = (self._idx + 1) % self.history_len
        self.blocks += 1
        if block_s and dt > block_s:
            self.overruns += 1

        if status:
            bad = False
            if getattr(status, "input_underflow", False):
                self.input_underflow += 1
                bad = True
            if getattr(status, "input_overflow", False):
                self.input_overflow += 1
                bad = True
            if getattr(status, "output_underflow", False):
                self.output_underflow += 1
                bad = True
            if getattr(status, "output_overflow", False):
                self.output_overflow += 1
                bad = True
            if bad:
                self.xruns += 1

    # ---- read from the GUI thread ------------------------------------- #
    def cpu_load(self):
        """Average load, 0.0 .. (can exceed 1.0 when overloaded)."""
        return self.avg_s / self.block_s if self.block_s else 0.0

    def peak_load(self):
        """Worst block since reset, as a fraction of the block time."""
        return self.max_s / self.block_s if self.block_s else 0.0

    def history_loads(self):
        """The last `history_len` blocks, oldest first, as fractions of the
        block time (a new array, safe to draw from)."""
        if not self.block_s:
            return np.zeros(self.history_len)
        h = np.roll(self.history, -self._idx)
        return h / self.block_s

    def summary(self):
        return {
            "blocks": self.blocks,
            "cpu_avg_pct": round(self.cpu_load() * 100.0, 1),
            "cpu_peak_pct": round(self.peak_load() * 100.0, 1),
            "last_ms": round(self.last_s * 1000.0, 3),
            "avg_ms": round(self.avg_s * 1000.0, 3),
            "max_ms": round(self.max_s * 1000.0, 3),
            "block_ms": round(self.block_s * 1000.0, 3),
            "xruns": self.xruns,
            "overruns": self.overruns,
            "input_underflow": self.input_underflow,
            "input_overflow": self.input_overflow,
            "output_underflow": self.output_underflow,
            "output_overflow": self.output_overflow,
        }


def short_mode(engine):
    """'WASAPI EXCL 48000/64', 'SHARED 48000/64' or the plain mode name."""
    cfg = getattr(engine, "active_config", None)
    if cfg is None:
        return str(getattr(engine, "mode_name", "IDLE"))
    mode = "WASAPI EXCL" if cfg.exclusive else "SHARED"
    if cfg.exclusive and getattr(cfg, "split", False):
        mode += " SPLIT"
    return f"{mode} {cfg.sample_rate}/{cfg.block_size}"


def rtt_text(engine):
    """'RTT 15.2 ms (measured)' when calibrated for the running mode, else
    'RTT 22.0 ms (reported, not measured)'."""
    m = engine.measured_rtt_ms() if hasattr(engine, "measured_rtt_ms") else None
    if m is not None:
        return f"RTT {m:.1f} ms (measured)"
    return f"RTT {engine.latency_ms():.1f} ms (reported, not measured)"


def format_status(engine, with_rtt=True):
    """The one-line status text, e.g.
    'WASAPI EXCL 48000/64 | RTT 15.2 ms (measured) | CPU 12% | xruns 0 | peak 0.42'
    Without a calibration it says 'reported (not measured)' (see rtt_text)."""
    tel = engine.telemetry
    peak = max(engine.peak_l, engine.peak_r)
    rtt = f" | {rtt_text(engine)}" if with_rtt else ""
    return (f"{short_mode(engine)}{rtt} | "
            f"CPU {tel.cpu_load() * 100:.0f}% | xruns {tel.xruns} | peak {peak:.2f}")


def load_color(load, peak):
    """Green normally, red when the CPU load is above 70 % or the output clips."""
    return "#FF3333" if (load > WARN_LOAD or peak >= 0.85) else "#00FF66"
