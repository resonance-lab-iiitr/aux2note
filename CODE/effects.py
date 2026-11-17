"""
effects.py
Real-time-safe DSP building blocks used by every track and by the master bus.

All effects are *stateful* (they carry filter memory / delay lines between
calls) so they can be fed one audio block at a time from the sounddevice
callback without clicks or discontinuities.
"""

import math

import numpy as np
from scipy.signal import lfilter


# --------------------------------------------------------------------------- #
# rc10 "clean audio" building blocks
# --------------------------------------------------------------------------- #
_RAMPS = {}


def _unit_ramp(n):
    """(1/n, 2/n, ... 1.0) - cached so the audio thread does not allocate."""
    r = _RAMPS.get(n)
    if r is None:
        r = (np.arange(1, n + 1, dtype=np.float64) / float(n))
        if len(_RAMPS) < 64:
            _RAMPS[n] = r
    return r


def _scalar(v):
    return isinstance(v, float)


class ParamSmoother:
    """One-pole smoothing of a control value (volume, mix, drive ...).

    A knob that jumps from one block to the next makes a click ("zipper
    noise"). step(target, n) returns either the plain float (nothing is
    moving, the fast path) or an array of n values gliding to the target with
    a time constant of `tc_ms`. The first call snaps to the target, so a
    freshly built effect never fades in from zero."""

    def __init__(self, sample_rate, tc_ms=10.0):
        self.a = float(math.exp(-1.0 / max(1.0, tc_ms * 0.001 * sample_rate)))
        self.cur = None

    def reset(self, value=None):
        self.cur = None if value is None else float(value)

    def step(self, target, n):
        target = float(target)
        cur = self.cur
        tol = 1e-5 * max(1.0, abs(target))
        if cur is None or abs(cur - target) <= tol:
            self.cur = target
            return target
        a = self.a
        y, _ = lfilter([1.0 - a], [1.0, -a], np.full(n, target), zi=[a * cur])
        last = float(y[-1])
        self.cur = target if abs(last - target) <= tol else last
        return y


def soft_limit(x, knee=0.8):
    """Transparent safety limiter for the master bus (replaces plain tanh).

    Below `knee` the signal passes unchanged (tanh bent even quiet signals).
    Above it the peaks are rounded smoothly toward, never past, +-1.0, with
    the same slope at the knee so there is no corner. It is a static soft
    clipper, not a look-ahead limiter (that would add latency)."""
    x = np.asarray(x)
    a = np.abs(x)
    if float(a.max(initial=0.0)) <= knee:
        return x
    room = 1.0 - knee
    over = np.sign(x) * (knee + room * np.tanh((a - knee) / room))
    return np.where(a > knee, over, x).astype(np.float32)


def flush_small(a, thr=1e-30):
    """Zero out values so tiny they could become denormal numbers (which
    can make the CPU 50-100x slower on a fading tail). -600 dBFS: inaudible."""
    m = np.abs(a) < thr
    if m.any():
        a[m] = 0.0


class DCBlocker:
    """~20 Hz one-pole high-pass: removes DC offset (thumps and pops when
    it hits a compressor or distortion)."""

    def __init__(self, sample_rate, cutoff_hz=20.0):
        self.r = 1.0 - 2.0 * math.pi * cutoff_hz / float(sample_rate)
        self.zi = np.zeros(1)

    def reset(self):
        self.zi = np.zeros(1)

    def process(self, x):
        y, self.zi = lfilter([1.0, -1.0], [1.0, -self.r], x, zi=self.zi)
        if abs(self.zi[0]) < 1e-30:
            self.zi[0] = 0.0
        return y.astype(np.float32)


class DownwardExpander:
    """Gentle noise expander. Below `threshold_db` the level is pushed further
    down (by (ratio-1) dB per dB below the threshold, at most `range_db`),
    so hiss and the noisy end of a fading note get quieter instead of being
    amplified by whatever comes after. Block-rate detector with a ramp across
    the block, so the gain never steps."""

    def __init__(self, sample_rate, threshold_db=-55.0, ratio=2.0, range_db=30.0,
                 attack_ms=1.0, release_ms=100.0):
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.range_db = range_db
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self._level = 0.0
        self._gain = 1.0

    def reset(self):
        self._level = 0.0
        self._gain = 1.0

    def process(self, x):
        n = len(x)
        if n == 0:
            return x
        t = n / float(self.sample_rate)
        peak = float(np.max(np.abs(x)))
        self._level = max(peak, self._level * math.exp(-t / 0.05), 1e-9)   # 50 ms detector release
        thr = 10.0 ** (self.threshold_db / 20.0)
        if self._level >= thr:
            target = 1.0
        else:
            red = (self.threshold_db - 20.0 * math.log10(self._level)) * (max(self.ratio, 1.0) - 1.0)
            target = 10.0 ** (-min(red, self.range_db) / 20.0)
        tau = (self.attack_ms if target > self._gain else self.release_ms) * 0.001
        g_new = target + (self._gain - target) * math.exp(-t / max(tau, 1e-6))
        if abs(g_new - target) < 1e-4:
            g_new = target
        if g_new == 1.0 and self._gain == 1.0:
            return x
        g = self._gain + (g_new - self._gain) * _unit_ramp(n)
        self._gain = g_new
        return (x * g).astype(np.float32)


class InputCleanup:
    """Live-input clean-up: DC blocker, then the gentle noise expander."""

    def __init__(self, sample_rate):
        self.dc = DCBlocker(sample_rate)
        self.expander = DownwardExpander(sample_rate)

    def reset(self):
        self.dc.reset()
        self.expander.reset()

    def process(self, x):
        return self.expander.process(self.dc.process(x))


# --------------------------------------------------------------------------- #
# Parametric / graphic EQ band (RBJ "Audio EQ Cookbook" biquad design)
# --------------------------------------------------------------------------- #
class EQBand:
    KIND_PEAK = "peak"
    KIND_LOWSHELF = "lowshelf"
    KIND_HIGHSHELF = "highshelf"

    def __init__(self, sample_rate, freq, gain_db=0.0, q=0.9, kind=KIND_PEAK):
        self.sample_rate = sample_rate
        self.freq = freq
        self.gain_db = gain_db
        self.q = q
        self.kind = kind
        self.b = [1.0, 0.0, 0.0]
        self.a = [1.0, 0.0, 0.0]
        self.zi = np.zeros(2)
        self._design()

    def _design(self):
        sr = self.sample_rate
        freq = min(max(self.freq, 20.0), sr / 2 - 100)
        A = 10 ** (self.gain_db / 40.0)
        w0 = 2 * np.pi * freq / sr
        cosw0 = np.cos(w0)
        sinw0 = np.sin(w0)
        alpha = sinw0 / (2 * max(self.q, 0.05))

        if self.kind == self.KIND_PEAK:
            b0 = 1 + alpha * A
            b1 = -2 * cosw0
            b2 = 1 - alpha * A
            a0 = 1 + alpha / A
            a1 = -2 * cosw0
            a2 = 1 - alpha / A
        elif self.kind == self.KIND_LOWSHELF:
            sqrtA = np.sqrt(A)
            b0 = A * ((A + 1) - (A - 1) * cosw0 + 2 * sqrtA * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cosw0)
            b2 = A * ((A + 1) - (A - 1) * cosw0 - 2 * sqrtA * alpha)
            a0 = (A + 1) + (A - 1) * cosw0 + 2 * sqrtA * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cosw0)
            a2 = (A + 1) + (A - 1) * cosw0 - 2 * sqrtA * alpha
        else:  # high shelf
            sqrtA = np.sqrt(A)
            b0 = A * ((A + 1) + (A - 1) * cosw0 + 2 * sqrtA * alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cosw0)
            b2 = A * ((A + 1) + (A - 1) * cosw0 - 2 * sqrtA * alpha)
            a0 = (A + 1) - (A - 1) * cosw0 + 2 * sqrtA * alpha
            a1 = 2 * ((A - 1) - (A + 1) * cosw0)
            a2 = (A + 1) - (A - 1) * cosw0 - 2 * sqrtA * alpha

        self.b = [b0 / a0, b1 / a0, b2 / a0]
        self.a = [1.0, a1 / a0, a2 / a0]

    def set_gain(self, gain_db):
        self.gain_db = gain_db
        self._design()

    def set_freq(self, freq):
        self.freq = freq
        self._design()

    def process(self, x):
        if abs(self.gain_db) < 0.001:
            return x
        y, self.zi = lfilter(self.b, self.a, x, zi=self.zi)
        if abs(self.zi[0]) + abs(self.zi[1]) < 1e-30:
            self.zi[:] = 0.0
        return y.astype(np.float32)

    def reset(self):
        self.zi = np.zeros(2)


# Standard 5-band "total equalizer" layout, mirrors a typical studio graphic EQ
DEFAULT_EQ_BANDS = [
    (60,    EQBand.KIND_LOWSHELF),
    (250,   EQBand.KIND_PEAK),
    (1000,  EQBand.KIND_PEAK),
    (4000,  EQBand.KIND_PEAK),
    (12000, EQBand.KIND_HIGHSHELF),
]


class Equalizer:
    """A full multi-band equalizer made of cascaded EQBand biquads."""

    def __init__(self, sample_rate, layout=None):
        layout = layout or DEFAULT_EQ_BANDS
        self.sample_rate = sample_rate
        self.bands = [EQBand(sample_rate, f, 0.0, 0.9, k) for f, k in layout]
        self.enabled = True

    def process(self, x):
        if not self.enabled:
            return x
        for band in self.bands:
            x = band.process(x)
        return x

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "bands": [{"freq": b.freq, "gain_db": b.gain_db, "q": b.q, "kind": b.kind} for b in self.bands],
        }

    def from_dict(self, d):
        self.enabled = d.get("enabled", True)
        for band, bd in zip(self.bands, d.get("bands", [])):
            band.freq = bd.get("freq", band.freq)
            band.gain_db = bd.get("gain_db", 0.0)
            band.q = bd.get("q", band.q)
            band._design()



# --------------------------------------------------------------------------- #
# Circular-buffer helpers (slice reads / writes, no per-sample Python loop)
# --------------------------------------------------------------------------- #
def _circ_read(buf, start, n):
    """Return a COPY of n samples starting at `start`, wrapping at len(buf)."""
    end = start + n
    if end <= len(buf):
        return buf[start:end].copy()
    k = len(buf) - start
    out = np.empty(n, dtype=buf.dtype)
    out[:k] = buf[start:]
    out[k:] = buf[:end - len(buf)]
    return out


def _circ_write(buf, start, data):
    n = len(data)
    end = start + n
    if end <= len(buf):
        buf[start:end] = data
        return
    k = len(buf) - start
    buf[start:] = data[:k]
    buf[:end - len(buf)] = data[k:]


# --------------------------------------------------------------------------- #
# Feedback delay / echo (vectorized)
# --------------------------------------------------------------------------- #
class Delay:
    MAX_FEEDBACK = 0.98          # safety clamp so extreme settings cannot blow up

    def __init__(self, sample_rate, time_sec=0.35, feedback=0.35, mix=0.25, max_seconds=3.0):
        self.sample_rate = sample_rate
        self.enabled = False
        self.time_sec = time_sec
        self.feedback = feedback
        self.mix = mix
        self._buf = np.zeros(int(max_seconds * sample_rate), dtype=np.float32)
        self._write = 0
        self._mix_s = ParamSmoother(sample_rate)
        self._d_prev = None          # delay length used by the previous block

    def reset_state(self):
        """Silence the delay line in place (no allocation)."""
        self._buf.fill(0.0)
        self._d_prev = None

    def process(self, x):
        if not self.enabled:
            return x
        n = len(x)
        buf = self._buf
        blen = len(buf)
        d = int(self.time_sec * self.sample_rate)
        d = max(1, min(d, blen - 1))
        d_old = d if self._d_prev is None else self._d_prev
        self._d_prev = d
        fade = d_old != d            # delay time moved: crossfade old tap -> new tap
        dmin = min(d, d_old)
        unit = _unit_ramp(n) if fade else None
        fb = min(max(self.feedback, 0.0), self.MAX_FEEDBACK)
        mix = self._mix_s.step(self.mix, n)
        out = np.empty(n, dtype=np.float32)
        w = self._write
        # A chunk may be as long as the delay: inside one chunk the samples we
        # read were all written before it started, so slices are exact.
        pos = 0
        while pos < n:
            m = min(dmin, n - pos)
            xs = x[pos:pos + m]
            delayed = _circ_read(buf, (w - d) % blen, m)
            if fade:
                old = _circ_read(buf, (w - d_old) % blen, m)
                delayed = old + (delayed - old) * unit[pos:pos + m]
            mx = mix if _scalar(mix) else mix[pos:pos + m]
            out[pos:pos + m] = xs + delayed * mx
            _circ_write(buf, w, xs + delayed * fb)
            w = (w + m) % blen
            pos += m
        self._write = w
        return out

    def to_dict(self):
        return {"enabled": self.enabled, "time_sec": self.time_sec, "feedback": self.feedback, "mix": self.mix}

    def from_dict(self, d):
        self.enabled = d.get("enabled", False)
        self.time_sec = d.get("time_sec", self.time_sec)
        self.feedback = d.get("feedback", self.feedback)
        self.mix = d.get("mix", self.mix)


# --------------------------------------------------------------------------- #
# Schroeder-style reverb (4 parallel combs -> 2 series allpass), vectorized
# --------------------------------------------------------------------------- #
class _Comb:
    def __init__(self, delay_len, feedback):
        self.buf = np.zeros(delay_len, dtype=np.float32)
        self.idx = 0
        self.feedback = feedback

    def process_chunk(self, x):
        """x is at most len(buf) samples long."""
        i, n = self.idx, len(x)
        out = _circ_read(self.buf, i, n)
        _circ_write(self.buf, i, x + out * self.feedback)
        self.idx = (i + n) % len(self.buf)
        return out


class _AllPass:
    def __init__(self, delay_len, gain=0.5):
        self.buf = np.zeros(delay_len, dtype=np.float32)
        self.idx = 0
        self.gain = gain

    def process_chunk(self, x):
        i, n = self.idx, len(x)
        buffered = _circ_read(self.buf, i, n)
        _circ_write(self.buf, i, x + buffered * self.gain)
        self.idx = (i + n) % len(self.buf)
        return buffered - x * self.gain

    def process_all(self, x):
        """Whole block, in chunks no longer than this all-pass's own delay line."""
        n, step = len(x), len(self.buf)
        if n <= step:
            return self.process_chunk(x)
        out = np.empty(n, dtype=np.float32)
        for pos in range(0, n, step):
            seg = x[pos:pos + step]
            out[pos:pos + len(seg)] = self.process_chunk(seg)
        return out


class Reverb:
    COMB_TUNINGS_MS = [29.7, 37.1, 41.1, 43.7]
    ALLPASS_TUNINGS_MS = [5.0, 1.7]

    def __init__(self, sample_rate, room_size=0.6, damping=0.3, mix=0.25):
        self.sample_rate = sample_rate
        self.enabled = False
        self.room_size = room_size
        self.mix = mix
        self.damping = damping
        self._fb_dirty = False
        self._mix_s = ParamSmoother(sample_rate)
        self._fb_s = ParamSmoother(sample_rate)
        self._build()

    @staticmethod
    def _feedback_for(room_size):
        return 0.6 + min(max(room_size, 0.0), 1.0) * 0.38      # 0.6 .. 0.98

    def _build(self):
        """Allocate the delay lines. Only called at start-up and by reset();
        a UI change never calls it, so a tail is never wiped."""
        sr = self.sample_rate
        fb = self._feedback_for(self.room_size)
        self.combs = [_Comb(max(2, int(sr * ms / 1000.0)), fb) for ms in self.COMB_TUNINGS_MS]
        self.allpasses = [_AllPass(max(2, int(sr * ms / 1000.0)), 0.5) for ms in self.ALLPASS_TUNINGS_MS]
        self._fb_target = fb
        self._fb_s.reset(fb)
        self._chunk = min(len(l.buf) for l in self.combs + self.allpasses)
        self._comb_chunk = min(len(c.buf) for c in self.combs)   # combs are long (>1400 samples)
        self._lp_state = 0.0

    def reset(self):
        self._build()

    def reset_state(self):
        """Silence all delay lines in place (no allocation, safe on the audio thread)."""
        for l in self.combs + self.allpasses:
            l.buf.fill(0.0)
        self._lp_state = 0.0

    def set_room_size(self, val):
        """UI thread. Only a float and a flag change; the audio thread picks the
        new comb feedback up at the start of its next block (buffers are kept)."""
        self.room_size = val
        self._fb_dirty = True

    def _apply_pending(self):
        self._fb_dirty = False                      # clear first, then read
        fb = self._feedback_for(self.room_size)
        for c in self.combs:
            c.feedback = fb

    def process(self, x):
        if not self.enabled:
            return x
        n = len(x)
        # A room-size change (set_room_size / project load) glides to the new
        # comb feedback over ~10 ms instead of jumping (no click).
        if self._fb_dirty:
            self._fb_dirty = False                  # clear first, then read
            self._fb_target = self._feedback_for(self.room_size)
        fbv = self._fb_s.step(self._fb_target, n)
        fb = fbv if _scalar(fbv) else float(fbv[-1])
        if fb != self.combs[0].feedback:
            for c in self.combs:
                c.feedback = fb
        d = min(max(self.damping, 0.0), 1.0)
        # damping low-pass: y[i] = y[i-1] + d*(x[i]-y[i-1])
        if d >= 1.0:
            lp = x.astype(np.float64)
        else:
            lp, _ = lfilter([d], [1.0, -(1.0 - d)], x, zi=[(1.0 - d) * self._lp_state])
        self._lp_state = float(lp[-1])
        if abs(self._lp_state) < 1e-30:
            self._lp_state = 0.0
        lp = lp.astype(np.float32)
        mix = self._mix_s.step(self.mix, n)
        # Stage by stage over the whole block. Each stage is causal and only
        # limited by its own delay length, so this gives the same samples as
        # the old "all stages per 81-sample chunk" loop with far fewer Python calls.
        cstep = self._comb_chunk
        if n <= cstep:
            wet = self.combs[0].process_chunk(lp)
            for c in self.combs[1:]:
                wet = wet + c.process_chunk(lp)
            wet = wet * 0.25
        else:
            wet = np.empty(n, dtype=np.float32)
            for pos in range(0, n, cstep):
                ls = lp[pos:pos + cstep]
                w = self.combs[0].process_chunk(ls)
                for c in self.combs[1:]:
                    w = w + c.process_chunk(ls)
                wet[pos:pos + len(ls)] = w * 0.25
        for ap in self.allpasses:
            wet = ap.process_all(wet)
        if _scalar(mix):
            return x + wet * mix
        return (x + wet * mix).astype(np.float32)

    def to_dict(self):
        return {"enabled": self.enabled, "room_size": self.room_size, "damping": self.damping, "mix": self.mix}

    def from_dict(self, d):
        self.enabled = d.get("enabled", False)
        self.room_size = d.get("room_size", self.room_size)
        self.damping = d.get("damping", self.damping)
        self.mix = d.get("mix", self.mix)
        self._fb_dirty = True                       # no rebuild, tail is kept

# --------------------------------------------------------------------------- #
# Soft-clip distortion / saturation
# --------------------------------------------------------------------------- #
def _logcosh(u):
    """ln(cosh(u)) without overflow."""
    a = np.abs(u)
    return a + np.log1p(np.exp(-2.0 * a)) - math.log(2.0)


class Distortion:
    """tanh saturation with first-order anti-derivative anti-aliasing (ADAA).

    A plain tanh makes harmonics above half the sample rate that fold back
    down as harsh, non-musical "digital" noise. ADAA replaces tanh(x) by the
    average of tanh over the step between two samples, which removes most of
    that folding at almost no CPU cost and with no latency. Drive range is
    1x-6x small-signal gain (was 1x-10x), so quiet tails and noise are
    boosted less."""
    DRIVE_SPAN = 5.0

    def __init__(self, drive=1.0, mix=1.0, sample_rate=48000):
        self.enabled = False
        self.drive = drive
        self.mix = mix
        self._drive_s = ParamSmoother(sample_rate)
        self._mix_s = ParamSmoother(sample_rate)
        self._xprev = 0.0
        self._fprev = 0.0            # ln(cosh(a*x)) of the previous sample ...
        self._a_prev = None          # ... and the gain `a` it was computed with

    def reset_state(self):
        self._xprev = 0.0
        self._fprev = 0.0
        self._a_prev = None

    def process(self, x):
        if not self.enabled:
            return x
        n = len(x)
        d = self._drive_s.step(self.drive, n)
        mix = self._mix_s.step(self.mix, n)
        a = 1.0 + d * self.DRIVE_SPAN
        x64 = x.astype(np.float64)
        xp = np.empty(n, dtype=np.float64)
        xp[0] = self._xprev
        xp[1:] = x64[:-1]
        self._xprev = float(x64[-1])
        dx = x64 - xp
        small = np.abs(dx) < 1e-7
        safe = np.where(small, 1.0, dx) if small.any() else dx
        F = _logcosh(a * x64)
        if _scalar(a):
            # steady drive: the previous sample's F is just F shifted by one
            Fp = np.empty(n, dtype=np.float64)
            Fp[0] = self._fprev if self._a_prev == a else float(_logcosh(a * xp[0]))
            Fp[1:] = F[:-1]
            self._a_prev = a
        else:                                       # drive is gliding
            Fp = _logcosh(a * xp)
            self._a_prev = float(a[-1])
        self._fprev = float(F[-1])
        wet = (F - Fp) / (a * safe)
        if small.any():                             # flat spots: use tanh at the midpoint
            mid = np.tanh(a * 0.5 * (x64 + xp))
            wet = np.where(small, mid, wet)
        wet = np.clip(wet / np.tanh(a), -1.0, 1.0)
        return (x * (1.0 - mix) + wet * mix).astype(np.float32)

    def to_dict(self):
        return {"enabled": self.enabled, "drive": self.drive, "mix": self.mix}

    def from_dict(self, d):
        self.enabled = d.get("enabled", False)
        self.drive = d.get("drive", self.drive)
        self.mix = d.get("mix", self.mix)


# --------------------------------------------------------------------------- #
# Dynamics compressor (vectorized envelope follower + soft-knee gain reduction)
# --------------------------------------------------------------------------- #
class Compressor:
    """Same maths as v1.1. The envelope follower is
        env[i] = c[i]*env[i-1] + (1-c[i])*|x[i]|,  c = attack if |x|>env else release
    which depends on its own past, so a plain Python loop was needed. Here the
    attack/release choice c[i] is first estimated for the whole block, then the
    recurrence for that c is solved in closed form with cumprod/cumsum, and the
    choice is refined (REFINE passes). Because env moves only ~0.3% per sample,
    the estimate is almost always already right; the golden test confirms it."""
    CHUNK = 256      # keeps cumprod far from float64 underflow
    REFINE = 1       # was 2; measured max error vs the v1.1 reference stays below -99 dBFS

    def __init__(self, sample_rate, threshold_db=-18.0, ratio=3.0, attack_ms=8.0,
                 release_ms=120.0, makeup_db=0.0):
        self.sample_rate = sample_rate
        self.enabled = False
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.makeup_db = makeup_db
        self._env = 1e-6
        self._th_s = ParamSmoother(sample_rate)
        self._ra_s = ParamSmoother(sample_rate)
        self._mk_s = ParamSmoother(sample_rate)

    def reset_state(self):
        self._env = 1e-6

    def _follow(self, rect, env0, atk, rel):
        """Envelope for one chunk (float64 in, float64 out)."""
        env = np.full(len(rect), env0)
        prev = env
        for _ in range(self.REFINE + 1):
            c = np.where(rect > prev, atk, rel)
            p = np.cumprod(c)
            env = p * (env0 + np.cumsum((1.0 - c) * rect / p))
            prev = np.empty_like(env)
            prev[0] = env0
            prev[1:] = env[:-1]
        return env

    def process(self, x):
        if not self.enabled:
            return x
        sr = self.sample_rate
        atk = np.exp(-1.0 / (0.001 * max(self.attack_ms, 0.0) * sr + 1))
        rel = np.exp(-1.0 / (0.001 * max(self.release_ms, 0.0) * sr + 1))
        rect = np.abs(x).astype(np.float64)
        n = len(rect)
        if n <= self.CHUNK:
            env_arr = self._follow(rect, self._env, atk, rel)
        else:
            env_arr = np.empty(n, dtype=np.float64)
            e = self._env
            for s in range(0, n, self.CHUNK):
                seg = self._follow(rect[s:s + self.CHUNK], e, atk, rel)
                env_arr[s:s + len(seg)] = seg
                e = float(seg[-1])
        self._env = max(float(env_arr[-1]), 1e-12)   # never decays into denormals
        # threshold / ratio / makeup glide to new values (no zipper noise)
        thresh = 10 ** (self._th_s.step(self.threshold_db, n) / 20.0)
        makeup = 10 ** (self._mk_s.step(self.makeup_db, n) / 20.0)
        k = 1.0 - 1.0 / np.maximum(self._ra_s.step(self.ratio, n), 1.0)   # 0 .. 1  (ratio < 1 would expand)
        over = np.maximum(env_arr, thresh) / thresh
        gain = np.where(env_arr > 1e-9, over ** (-k), 1.0)
        return (x * (gain * makeup)).astype(np.float32)

    def to_dict(self):
        return {
            "enabled": self.enabled, "threshold_db": self.threshold_db, "ratio": self.ratio,
            "attack_ms": self.attack_ms, "release_ms": self.release_ms, "makeup_db": self.makeup_db,
        }

    def from_dict(self, d):
        self.enabled = d.get("enabled", False)
        self.threshold_db = d.get("threshold_db", self.threshold_db)
        self.ratio = d.get("ratio", self.ratio)
        self.attack_ms = d.get("attack_ms", self.attack_ms)
        self.release_ms = d.get("release_ms", self.release_ms)
        self.makeup_db = d.get("makeup_db", self.makeup_db)


# --------------------------------------------------------------------------- #
# Per-track effects chain: EQ -> Compressor -> Distortion -> Delay -> Reverb
# --------------------------------------------------------------------------- #
class EffectsChain:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.eq = Equalizer(sample_rate)
        self.compressor = Compressor(sample_rate)
        self.distortion = Distortion(sample_rate=sample_rate)
        self.delay = Delay(sample_rate)
        self.reverb = Reverb(sample_rate)
        self._flush_cursor = 0

    def reset_state(self):
        """Forget all filter / delay memory in place. Called when a tail has
        died away, so nothing stale is left to click on the next note."""
        for b in self.eq.bands:
            b.reset()
        self.compressor.reset_state()
        self.distortion.reset_state()
        self.delay.reset_state()
        self.reverb.reset_state()

    FLUSH_STEPS = 8

    def flush_denormals(self):
        """Zero values small enough to turn into slow denormal numbers.
        Does 1/8 of the work per call (call it every ~40 ms on always-running
        chains) so no single audio block pays for the whole sweep."""
        k = self._flush_cursor
        self._flush_cursor = (k + 1) % self.FLUSH_STEPS
        if k == 0:
            for b in self.eq.bands:
                flush_small(b.zi)
            if self.compressor._env < 1e-12:
                self.compressor._env = 1e-12
        elif k == 1:
            if self.delay.enabled:
                flush_small(self.delay._buf)
        elif 2 <= k <= 5:
            if self.reverb.enabled:
                flush_small(self.reverb.combs[k - 2].buf)
        elif k == 6:
            if self.reverb.enabled:
                for l in self.reverb.allpasses:
                    flush_small(l.buf)

    def process(self, x):
        x = self.eq.process(x)
        x = self.compressor.process(x)
        x = self.distortion.process(x)
        x = self.delay.process(x)
        x = self.reverb.process(x)
        return x

    def clone(self):
        """Return a fresh chain with identical parameters but empty filter memory,
        used for offline (non-realtime) mixdown rendering."""
        c = EffectsChain(self.sample_rate)
        c.from_dict(self.to_dict())
        return c

    def to_dict(self):
        return {
            "eq": self.eq.to_dict(),
            "compressor": self.compressor.to_dict(),
            "distortion": self.distortion.to_dict(),
            "delay": self.delay.to_dict(),
            "reverb": self.reverb.to_dict(),
        }

    def from_dict(self, d):
        if "eq" in d:
            self.eq.from_dict(d["eq"])
        if "compressor" in d:
            self.compressor.from_dict(d["compressor"])
        if "distortion" in d:
            self.distortion.from_dict(d["distortion"])
        if "delay" in d:
            self.delay.from_dict(d["delay"])
        if "reverb" in d:
            self.reverb.from_dict(d["reverb"])


# --------------------------------------------------------------------------- #
# Quick benchmark (used by tools/dsp_bench.py and the FX dialog cost labels)
# --------------------------------------------------------------------------- #
def benchmark_costs(sample_rate=48000, block=64, reps=300):
    """Cost of each effect (and of the whole chain with everything on) as a
    percent of one audio block's duration. Takes well under a second."""
    import time
    rs = np.random.RandomState(0)
    x = (0.3 * rs.randn(block)).astype(np.float32)
    budget = block / float(sample_rate)

    def cost(chain):
        for _ in range(20):                       # warm-up
            chain.process(x)
        best = float("inf")
        for _ in range(3):                        # best of 3 rejects OS hiccups
            t0 = time.perf_counter()
            for _ in range(reps):
                chain.process(x)
            best = min(best, (time.perf_counter() - t0) / reps)
        return 100.0 * best / budget

    def chain_with(**on):
        c = EffectsChain(sample_rate)
        for name in on:
            if name == "eq":
                for b in c.eq.bands:
                    b.set_gain(3.0)
            else:
                getattr(c, name).enabled = True
        return c

    out = {}
    for label, key in (("EQ (5 band)", "eq"), ("Compressor", "compressor"),
                       ("Distortion", "distortion"), ("Delay", "delay"), ("Reverb", "reverb")):
        out[label] = cost(chain_with(**{key: True}))
    out["ALL (chain)"] = cost(chain_with(eq=1, compressor=1, distortion=1, delay=1, reverb=1))
    return out
