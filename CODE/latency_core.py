"""
latency_core.py  (Live Looper Pro v2.0, Phase 5)

Latency measurement shared by the GUI (AudioEngine.run_calibration) and the
CLI (latency_lab.py). Pure numpy: no sound card, no Tk.

  make_chirp / build_signal / analyze   moved unchanged from latency_lab.py
  Calibrator                            drives one measurement inside a callback
  summarize                             analyze() output -> RTT, jitter, level, status
"""
import math

import numpy as np

LEAD_S, GAP_S, TAIL_S = 1.0, 0.7, 0.8


# ----------------------------------------------------------------------------
# Signal + analysis (pure numpy; testable without audio hardware)
# ----------------------------------------------------------------------------
def make_chirp(fs, dur=0.03, f0=300.0, f1=12000.0):
    f1 = min(f1, 0.45 * fs)
    n = int(fs * dur)
    t = np.arange(n) / fs
    k = math.log(f1 / f0)
    phase = 2 * math.pi * f0 * dur / k * (np.exp(t / dur * k) - 1.0)
    return (np.sin(phase) * np.hanning(n)).astype(np.float32)


def build_signal(fs, nbursts):
    chirp = make_chirp(fs)
    starts = [int(fs * (LEAD_S + i * GAP_S)) for i in range(nbursts)]
    total = int(fs * (LEAD_S + nbursts * GAP_S + TAIL_S))
    sig = np.zeros(total, np.float32)
    for s in starts:
        sig[s:s + len(chirp)] = chirp
    return sig, starts, chirp, total


def analyze(rec, fs, starts, chirp, ncc_min=0.35):
    """Return per-burst delays (ms, NaN if missed) plus level/noise metrics."""
    L = len(chirp)
    rec = np.asarray(rec, dtype=np.float64)
    n = len(rec) + L - 1
    nfft = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(rec, nfft) * np.fft.rfft(chirp[::-1].astype(np.float64), nfft), nfft)[:n]
    csum = np.concatenate(([0.0], np.cumsum(rec ** 2)))
    m = np.arange(n)
    energy = csum[np.minimum(m + 1, len(rec))] - csum[np.maximum(m - L + 1, 0)]
    cn = float(np.sqrt(np.sum(chirp.astype(np.float64) ** 2)))
    ncc = np.abs(corr) / (np.sqrt(energy) * cn + 1e-12)
    absc = np.abs(corr)
    gap = int(GAP_S * fs)
    delays, nccs, peaks = [], [], []
    for s in starts:
        a, b = s + L - 1, min(s + L - 1 + gap, n - 1)
        if b - a < 3:
            delays.append(float("nan")); nccs.append(0.0); peaks.append(float("nan")); continue
        seg = absc[a:b]
        k = int(np.argmax(seg))
        off = 0.0
        if 0 < k < len(seg) - 1:
            y0, y1, y2 = seg[k - 1], seg[k], seg[k + 1]
            d = y0 - 2 * y1 + y2
            off = 0.5 * (y0 - y2) / d if d != 0 else 0.0
        c = float(ncc[a + k])
        nccs.append(c)
        if c < ncc_min:
            delays.append(float("nan")); peaks.append(float("nan")); continue
        d_samples = (a + k + off - (L - 1)) - s
        delays.append(d_samples / fs * 1000.0)
        i0 = int(s + d_samples)
        peaks.append(float(np.max(np.abs(rec[i0:i0 + L]))) if i0 + L <= len(rec) else float("nan"))
    noise = rec[int(0.3 * fs):int(0.9 * fs)]
    noise_rms = float(np.sqrt(np.mean(noise ** 2))) if len(noise) else 0.0
    pk = np.nanmax(peaks) if not np.all(np.isnan(peaks)) else float("nan")
    db = lambda v: 20 * math.log10(v) if v and v > 1e-9 else -120.0
    return {
        "delays_ms": delays,
        "ncc": nccs,
        "peak_dbfs": db(pk) if not math.isnan(pk) else -120.0,
        "peak_lin": pk,
        "noise_dbfs": db(noise_rms),
    }


# ----------------------------------------------------------------------------
# Phase 5: in-callback measurement + verdict
# ----------------------------------------------------------------------------
STATUS_OK = "OK"
STATUS_QUIET = "TOO QUIET"
STATUS_CLIP = "CLIPPING"
STATUS_NONE = "NO SIGNAL"
CLIP_LEVEL = 0.98          # captured peak at or above this = clipping
QUIET_DBFS = -40.0         # captured chirp peak below this = too quiet
NOSIGNAL_PEAK = 0.002      # whole recording below this = nothing connected
DEFAULT_LEVEL = 0.35
DEFAULT_BURSTS = 6


class Calibrator:
    """One measurement. The engine callback calls process() every block:
    it plays the chirp train on every output channel and stores input
    channel 0. Output sample i and input sample i belong to the same
    callback position, so the chirp delay found by analyze() is the full
    round trip. No allocation in process()."""

    def __init__(self, fs, bursts=DEFAULT_BURSTS, level=DEFAULT_LEVEL):
        self.fs = int(fs)
        self.level = float(level)
        self.sig, self.starts, self.chirp, self.total = build_signal(self.fs, bursts)
        self.sig = (self.sig * self.level).astype(np.float32)
        self.rec = np.zeros(self.total + self.fs // 2, dtype=np.float32)
        self.pos = 0
        self.done = False

    def process(self, indata, outdata, frames):
        outdata.fill(0)
        if self.done:
            return
        pos = self.pos
        n = min(frames, max(0, self.total - pos))
        if n > 0:
            outdata[:n, :] = self.sig[pos:pos + n, None]
        room = max(0, min(frames, len(self.rec) - pos))
        if room > 0 and indata.shape[1] > 0:
            self.rec[pos:pos + room] = indata[:room, 0]
        self.pos = pos + frames
        if self.pos >= self.total + self.fs // 4:
            self.done = True

    def result(self):
        return summarize(self.rec[:min(self.pos, len(self.rec))], self.fs,
                         self.starts, self.chirp)


def summarize(rec, fs, starts, chirp):
    """Return dict: status, rtt_ms, rtt_samples, jitter_ms (max-min of the
    bursts), level_dbfs, rec_peak, bursts_ok, bursts."""
    res = analyze(rec, fs, starts, chirp)
    rec_peak = float(np.max(np.abs(rec))) if len(rec) else 0.0
    good = [d for d in res["delays_ms"] if not math.isnan(d)]
    need = max(3, (len(starts) + 1) // 2)
    out = dict(status=STATUS_NONE, rtt_ms=None, rtt_samples=None, jitter_ms=None,
               level_dbfs=res["peak_dbfs"], rec_peak=rec_peak,
               bursts_ok=len(good), bursts=len(starts))
    if len(good) < need:
        if rec_peak < NOSIGNAL_PEAK:
            out["status"] = STATUS_NONE
        elif rec_peak >= CLIP_LEVEL:
            out["status"] = STATUS_CLIP
        elif rec_peak < 0.02:
            out["status"] = STATUS_QUIET
        return out
    rtt = float(np.median(good))
    out["rtt_ms"] = rtt
    out["rtt_samples"] = int(round(rtt * fs / 1000.0))
    out["jitter_ms"] = float(max(good) - min(good))
    if res["peak_lin"] >= CLIP_LEVEL or rec_peak >= CLIP_LEVEL:
        out["status"] = STATUS_CLIP
    elif res["peak_dbfs"] < QUIET_DBFS:
        out["status"] = STATUS_QUIET
    else:
        out["status"] = STATUS_OK
    return out


ADVICE = {
    STATUS_OK: "Calibration saved.",
    STATUS_QUIET: "Signal too quiet. Raise the Windows playback volume or the line-in level.",
    STATUS_CLIP: "Signal clipping. Lower the Windows playback volume (the CLI test used --level 0.1), then try again.",
    STATUS_NONE: "No signal heard. Connect a cable from Line Out (green) to Line In (blue), "
                 "switch off 'Listen to this device', and try again.",
}
