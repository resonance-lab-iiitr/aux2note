"""Reference (v1.1) per-sample DSP, kept only so tests can compare the
vectorized effects against the original maths. Do not use in the app."""
import numpy as np


class DelayReference:
    def __init__(self, sample_rate, time_sec=0.35, feedback=0.35, mix=0.25, max_seconds=3.0):
        self.sample_rate = sample_rate
        self.enabled = False
        self.time_sec = time_sec
        self.feedback = feedback
        self.mix = mix
        self._buf = np.zeros(int(max_seconds * sample_rate), dtype=np.float32)
        self._write = 0

    def process(self, x):
        if not self.enabled:
            return x
        n = len(x)
        buf = self._buf
        blen = len(buf)
        delay_samples = int(self.time_sec * self.sample_rate)
        delay_samples = max(1, min(delay_samples, blen - 1))
        out = np.empty(n, dtype=np.float32)
        w = self._write
        fb = self.feedback
        mix = self.mix
        for i in range(n):
            read_idx = (w - delay_samples) % blen
            delayed = buf[read_idx]
            out[i] = x[i] + delayed * mix
            buf[w] = x[i] + delayed * fb
            w = (w + 1) % blen
        self._write = w
        return out

    def to_dict(self):
        return {"enabled": self.enabled, "time_sec": self.time_sec, "feedback": self.feedback, "mix": self.mix}

    def from_dict(self, d):
        self.enabled = d.get("enabled", False)
        self.time_sec = d.get("time_sec", self.time_sec)
        self.feedback = d.get("feedback", self.feedback)
        self.mix = d.get("mix", self.mix)




class _Comb:
    def __init__(self, delay_len, feedback):
        self.buf = np.zeros(delay_len, dtype=np.float32)
        self.idx = 0
        self.feedback = feedback

    def process_sample(self, x):
        out = self.buf[self.idx]
        self.buf[self.idx] = x + out * self.feedback
        self.idx = (self.idx + 1) % len(self.buf)
        return out


class _AllPass:
    def __init__(self, delay_len, gain=0.5):
        self.buf = np.zeros(delay_len, dtype=np.float32)
        self.idx = 0
        self.gain = gain

    def process_sample(self, x):
        buffered = self.buf[self.idx]
        out = -x * self.gain + buffered
        self.buf[self.idx] = x + buffered * self.gain
        self.idx = (self.idx + 1) % len(self.buf)
        return out


class ReverbReference:
    COMB_TUNINGS_MS = [29.7, 37.1, 41.1, 43.7]
    ALLPASS_TUNINGS_MS = [5.0, 1.7]

    def __init__(self, sample_rate, room_size=0.6, damping=0.3, mix=0.25):
        self.sample_rate = sample_rate
        self.enabled = False
        self.room_size = room_size
        self.mix = mix
        self.damping = damping
        self._build()

    def _build(self):
        sr = self.sample_rate
        fb = 0.6 + self.room_size * 0.38  # 0.6 .. 0.98
        self.combs = [_Comb(max(2, int(sr * ms / 1000.0)), fb) for ms in self.COMB_TUNINGS_MS]
        self.allpasses = [_AllPass(max(2, int(sr * ms / 1000.0)), 0.5) for ms in self.ALLPASS_TUNINGS_MS]
        self._lp_state = 0.0

    def set_room_size(self, val):
        self.room_size = val
        self._build()

    def process(self, x):
        if not self.enabled:
            return x
        n = len(x)
        out = np.empty(n, dtype=np.float32)
        damp = self.damping
        lp = self._lp_state
        for i in range(n):
            s = x[i]
            # simple damping low-pass feeding the comb network for a darker tail
            lp = lp + damp * (s - lp)
            wet = 0.0
            for c in self.combs:
                wet += c.process_sample(lp)
            wet *= 0.25
            for ap in self.allpasses:
                wet = ap.process_sample(wet)
            out[i] = s + wet * self.mix
        self._lp_state = lp
        return out

    def to_dict(self):
        return {"enabled": self.enabled, "room_size": self.room_size, "damping": self.damping, "mix": self.mix}

    def from_dict(self, d):
        self.enabled = d.get("enabled", False)
        self.room_size = d.get("room_size", self.room_size)
        self.damping = d.get("damping", self.damping)
        self.mix = d.get("mix", self.mix)
        self._build()




class CompressorReference:
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

    def process(self, x):
        if not self.enabled:
            return x
        sr = self.sample_rate
        atk = np.exp(-1.0 / (0.001 * self.attack_ms * sr + 1))
        rel = np.exp(-1.0 / (0.001 * self.release_ms * sr + 1))
        thresh = 10 ** (self.threshold_db / 20.0)
        makeup = 10 ** (self.makeup_db / 20.0)
        out = np.empty_like(x)
        env = self._env
        for i in range(len(x)):
            rect = abs(x[i])
            coeff = atk if rect > env else rel
            env = coeff * env + (1 - coeff) * rect
            if env > thresh and env > 1e-9:
                over_db = 20 * np.log10(env / thresh)
                reduction_db = over_db * (1 - 1.0 / self.ratio)
                gain = 10 ** (-reduction_db / 20.0)
            else:
                gain = 1.0
            out[i] = x[i] * gain * makeup
        self._env = env
        return out.astype(np.float32)

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


