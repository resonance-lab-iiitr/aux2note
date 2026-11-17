"""
crackle_core.py  (Live Looper Pro v2.0, Phase 10 Crackle Lab, T018)

Finds clicks, dropouts, clipping, DC offset and mains hum in a recording and
says what they point to. Pure NumPy / SciPy: no Tk, no sounddevice, no engine
import, so it runs in the sandbox and on the user's PC.

  load_audio(path)                  -> (mono float64 array, sample rate)
  ms_features(x, sr)                -> one row per millisecond (dict of arrays)
  detect_clicks(x, sr)              -> list of click events (AR prediction residual)
  detect_dropouts(x, sr)            -> zero runs and repeated-sample runs inside signal
  detect_clipping(x)                -> samples held at +/- full scale, with run lengths
  dc_and_noise_floor(x, sr)         -> DC offset and noise floor in dBFS
  hum_peaks(x, sr)                  -> 50 / 60 Hz hum and harmonics
  block_alignment(events, block)    -> do events cluster at one offset inside the audio block?
  correlate_with_blocks(events, t)  -> do events sit next to late blocks, PortAudio
                                       status flags or ADC-time gaps?
  analyze(x, sr, ...)               -> all of the above in one report dict
  verdict(report)                   -> ranked hypotheses with evidence and a next test

blocks_table (for correlate_with_blocks / analyze) is a dict of equal-length
lists or arrays, a list of row dicts, or a numpy structured array, with any of:
  start     sample index in the capture where the block starts (else built
            from `frames`, else from the block_size argument)
  frames    frames in the block
  cb_ms     time the callback needed, milliseconds  (late = cb_ms > block time)
  late      0/1, overrides cb_ms
  status    PortAudio status bit flags, 0 = fine (1 input underflow,
            2 input overflow, 4 output underflow, 8 output overflow)
  adc_time  PortAudio input ADC time of the block, seconds

Verdict rules are HYPOTHESES, never certainty. Each has a confidence of low,
medium or high, the evidence lines and the next test to run.

LIMIT: Claude and this code judge numbers and pictures (sample values,
spectra, timing), not how a recording sounds. A click that the detector
reports may be inaudible and an audible crackle may be below its thresholds.
"""
import math

import numpy as np
from scipy import signal as _sig
from scipy import stats as _stats

# ---- tunable thresholds (also quoted in the tests) ------------------------- #
CLICK_K = 14.0                # click = AR residual above K * local robust sigma
CLICK_FLOOR = 10.0 ** (-90.0 / 20.0)   # residual below -90 dBFS is never a click
AR_ORDER = 12
AR_FRAME = 1024               # samples per LPC frame
AR_REG = 1e-6                 # white-noise correction on the autocorrelation
SCALE_HOP_MS = 2.0            # robust-scale frame length
MERGE_GAP = 16                # residual hits closer than this (samples) are one event
CLIP_THRESHOLD = 0.999
SILENCE_DB = -70.0            # context quieter than this = digital silence, not a dropout
MIN_EVENTS = 3                # fewer events than this never make a verdict
BAND_EDGES_HZ = (0.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 12000.0, 16000.0, float("inf"))

STATUS_BITS = {"input_underflow": 1, "input_overflow": 2,
               "output_underflow": 4, "output_overflow": 8}

DISCLAIMER = ("Judged from numbers (samples, spectra, timing), not from listening. "
              "These are hypotheses, not proof.")


def _db(v, floor=1e-12):
    return 20.0 * math.log10(max(float(v), floor))


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def load_audio(path, channel=None):
    """Read a WAV / FLAC file. Returns (x, sr): float64 mono (channels averaged,
    or `channel` if given) and the sample rate."""
    import soundfile as sf
    data, sr = sf.read(str(path), dtype="float64", always_2d=True)
    if channel is not None:
        x = data[:, int(channel)]
    else:
        x = data.mean(axis=1)
    return np.ascontiguousarray(x), int(sr)


# ----------------------------------------------------------------------------
# Per-millisecond features
# ----------------------------------------------------------------------------
def ms_features(x, sr):
    """One row per millisecond (frame = round(sr/1000) samples, a trailing
    partial frame is dropped). Returns a dict of numpy arrays, each with one
    entry per row: time_s, peak, rms, dc, max_step, zero_crossings, hf_ratio
    (share of spectral energy above 8 kHz), centroid_hz, dominant_hz,
    clip_count, plus `band_db` (rows x 8, dB, see `band_edges_hz`).
    Spectral values come from a 1 ms Hann-windowed FFT, so their real frequency
    resolution is about 1 kHz: the two lowest bands blend together."""
    x = np.asarray(x, dtype=np.float64)
    fr = max(int(round(sr / 1000.0)), 4)
    n = len(x) // fr
    if n == 0:
        z = np.zeros(0)
        return {"time_s": z, "peak": z, "rms": z, "dc": z, "max_step": z,
                "zero_crossings": z.astype(int), "hf_ratio": z, "centroid_hz": z,
                "dominant_hz": z, "clip_count": z.astype(int),
                "band_db": np.zeros((0, 8)), "band_edges_hz": BAND_EDGES_HZ,
                "frame": fr}
    X = x[:n * fr].reshape(n, fr)
    ax = np.abs(X)
    sign = np.signbit(X)
    nfft = 128
    P = np.abs(np.fft.rfft(X * np.hanning(fr), nfft, axis=1)) ** 2
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    tot = P.sum(axis=1)
    safe = np.where(tot > 0, tot, 1.0)
    hf = P[:, f >= 8000.0].sum(axis=1) / safe if sr / 2.0 > 8000.0 else np.zeros(n)
    cen = (P * f).sum(axis=1) / safe
    dom = f[np.argmax(P[:, 1:], axis=1) + 1]
    bands = np.zeros((n, 8))
    for i in range(8):
        m = (f >= BAND_EDGES_HZ[i]) & (f < BAND_EDGES_HZ[i + 1])
        bands[:, i] = 10.0 * np.log10(P[:, m].sum(axis=1) / (fr * fr) + 1e-12) if m.any() else -120.0
    return {
        "time_s": np.arange(n) * fr / float(sr),
        "peak": ax.max(axis=1),
        "rms": np.sqrt((X ** 2).mean(axis=1)),
        "dc": X.mean(axis=1),
        "max_step": np.abs(np.diff(X, axis=1)).max(axis=1),
        "zero_crossings": (sign[:, 1:] != sign[:, :-1]).sum(axis=1),
        "hf_ratio": hf,
        "centroid_hz": cen,
        "dominant_hz": dom,
        "clip_count": (ax >= CLIP_THRESHOLD).sum(axis=1),
        "band_db": bands,
        "band_edges_hz": BAND_EDGES_HZ,
        "frame": fr,
    }


def features_to_rows(feats):
    """ms_features() output -> list of plain dicts, one per millisecond
    (band energies as band0_db .. band7_db). Handy for CSV writers."""
    n = len(feats["peak"])
    rows = []
    scalar_keys = ("time_s", "peak", "rms", "dc", "max_step", "zero_crossings",
                   "hf_ratio", "centroid_hz", "dominant_hz", "clip_count")
    for i in range(n):
        r = {k: float(feats[k][i]) if k not in ("zero_crossings", "clip_count") else int(feats[k][i])
             for k in scalar_keys}
        for b in range(8):
            r["band%d_db" % b] = float(feats["band_db"][i, b])
        rows.append(r)
    return rows


# ----------------------------------------------------------------------------
# Clicks
# ----------------------------------------------------------------------------
def _ar_residual(x, order=AR_ORDER, frame=AR_FRAME, reg=AR_REG):
    """Prediction residual of a per-frame autoregressive model (autocorrelation
    method, Hann window, white-noise correction `reg`). A steady tone, hiss or
    voiced sound is predictable, so its residual is small; a click, a step or
    a dropout edge is not predictable and stands out. Vectorised over frames."""
    n = len(x)
    nf = int(math.ceil(n / float(frame)))
    total = nf * frame
    xp = np.zeros(order + total)
    xp[order:order + n] = x
    # context at the very start is zero; mark those samples invalid afterwards
    res = np.zeros(total)
    win = np.hanning(frame)
    ii = np.abs(np.arange(order)[:, None] - np.arange(order)[None, :])
    nfft = 1 << (2 * frame - 1).bit_length()
    chunk = 2048
    for f0 in range(0, nf, chunk):
        f1 = min(nf, f0 + chunk)
        base = np.arange(f0, f1)[:, None] * frame
        seg = xp[base + np.arange(frame + order)[None, :]]       # (Fc, frame+order)
        cur = seg[:, order:]
        Xf = np.fft.rfft(cur * win, nfft, axis=1)
        r = np.fft.irfft(np.abs(Xf) ** 2, nfft, axis=1)[:, :order + 1]
        r[:, 0] = r[:, 0] * (1.0 + reg) + 1e-12
        R = r[:, ii]
        b = r[:, 1:order + 1]
        try:
            w = np.linalg.solve(R, b[..., None])[..., 0]
        except np.linalg.LinAlgError:
            w = np.zeros_like(b)
        pred = np.zeros_like(cur)
        for k in range(1, order + 1):
            pred += w[:, k - 1:k] * seg[:, order - k:order - k + frame]
        res[f0 * frame:f1 * frame] = (cur - pred).reshape(-1)
    res = res[:n]
    res[:order] = 0.0
    return res


def _local_scale(res, sr, hop_ms=SCALE_HOP_MS):
    """Robust noise scale of the residual per sample: median |r| of each 2 ms
    frame (-> sigma for Gaussian noise), widened to the loudest neighbour
    frame so a quiet frame next to a burst is not over-sensitive."""
    hop = max(int(round(sr * hop_ms / 1000.0)), 8)
    n = len(res)
    nh = int(math.ceil(n / float(hop)))
    pad = np.zeros(nh * hop)
    pad[:n] = np.abs(res)
    pad[n:] = np.median(pad[:n]) if n else 0.0
    m = np.median(pad.reshape(nh, hop), axis=1) / 0.6745
    mm = m.copy()
    if nh > 1:
        mm[1:] = np.maximum(mm[1:], m[:-1])
        mm[:-1] = np.maximum(mm[:-1], m[1:])
    return np.repeat(mm, hop)[:n]


def _hf_track(x, sr):
    fc = min(8000.0, 0.4 * sr)
    sos = _sig.butter(4, fc, btype="highpass", fs=sr, output="sos")
    return _sig.sosfiltfilt(sos, x) if len(x) > 40 else x * 0.0


def detect_clicks(x, sr, k=CLICK_K, block_size=None, first_block_start=0):
    """Find clicks: short unpredictable jumps (1 to ~100 samples).

    Method: AR prediction residual (order 12, per 1024-sample frame) compared
    with a robust local sigma (median based, 2 ms frames); a hit is a residual
    above k * sigma and above -90 dBFS. Hits closer than 16 samples are merged.
    Width and amplitude are measured against a straight line drawn across the
    event (approximate, for ranking, not exact). Events where a sound simply
    starts or stops (level jump > 18 dB, event small next to the loud side) are
    dropped as onsets.

    Each event is a dict: start, end, width, amplitude, score (peak residual /
    sigma), hf_db (energy above 8 kHz within about 0.5 ms, dBFS), time_s and,
    when block_size is given, block_offset (start inside its audio block)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 4 * AR_ORDER:
        return []
    res = _ar_residual(x)
    scale = _local_scale(res, sr)
    thr = np.maximum(k * scale, CLICK_FLOOR)
    hit = np.flatnonzero(np.abs(res) > thr)
    if hit.size == 0:
        return []
    cuts = np.flatnonzero(np.diff(hit) > MERGE_GAP)
    first = np.concatenate(([0], cuts + 1))
    last = np.concatenate((cuts, [hit.size - 1]))
    hp = _hf_track(x, sr)
    half = max(int(sr * 0.0005), 4)
    events = []
    for a, b in zip(first, last):
        s, e = int(hit[a]), int(hit[b])
        lo, hi = max(s - 3, 0), min(e + 3, n - 1)
        # width / amplitude: deviation from a line across the event
        # (the residual keeps ringing after the click, so measure in x itself)
        seg_end = min(s + 24, hi)
        xs, xe = x[lo], x[seg_end]
        line = np.linspace(xs, xe, seg_end - lo + 1)
        dev = np.abs(x[lo:seg_end + 1] - line)
        amp = float(dev.max())
        mask = dev >= max(0.25 * amp, 1e-12)
        idx = np.flatnonzero(mask)
        cs = lo + int(idx[0])
        ce = lo + int(idx[-1])
        # a sound starting or stopping (level jumps by > 18 dB around the event and
        # the event is small next to the loud side) is an onset, not a click
        w = max(int(sr * 0.002), 8)
        pre = math.sqrt(float(np.mean(x[max(cs - w, 0):cs] ** 2))) if cs > 0 else 0.0
        post = math.sqrt(float(np.mean(x[ce + 1:ce + 1 + w] ** 2))) if ce + 1 < n else 0.0
        lo_l, hi_l = min(pre, post), max(pre, post)
        if hi_l > 8.0 * max(lo_l, 1e-9) and amp < 0.25 * hi_l:
            continue
        pk = float(np.max(np.abs(res[s:e + 1]) / np.maximum(scale[s:e + 1], 1e-12)))
        seg = hp[max(cs - half, 0):min(ce + half + 1, n)]
        ev = {
            "start": cs,
            "end": ce,
            "width": ce - cs + 1,
            "amplitude": amp,
            "score": pk,
            "hf_db": _db(math.sqrt(float(np.mean(seg ** 2))) if seg.size else 0.0),
            "time_s": cs / float(sr),
        }
        if block_size:
            ev["block_offset"] = int((cs - first_block_start) % block_size)
        events.append(ev)
    return events


# ----------------------------------------------------------------------------
# Dropouts, clipping
# ----------------------------------------------------------------------------
def _runs(mask):
    """(start, length) of every run of True in a boolean array."""
    if mask.size == 0:
        return np.zeros(0, int), np.zeros(0, int)
    m = np.concatenate(([False], mask, [False])).astype(np.int8)
    d = np.diff(m)
    st = np.flatnonzero(d == 1)
    en = np.flatnonzero(d == -1)
    return st, en - st


def _context_rms(x, s, e, ctx):
    """RMS of the quieter side of [s, e): a dropout needs signal on BOTH sides
    (digital silence after the end of a sound, or before the start, is not one)."""
    a = x[max(s - ctx, 0):s]
    b = x[e:e + ctx]
    ra = math.sqrt(float(np.mean(a ** 2))) if a.size else 0.0
    rb = math.sqrt(float(np.mean(b ** 2))) if b.size else 0.0
    return min(ra, rb)


def detect_dropouts(x, sr, min_len=None, include_silence=False, block_size=None,
                    first_block_start=0):
    """Runs of exact zeros ("zero") or of one repeated sample value ("repeat",
    what a driver does when it re-sends the last sample) that sit INSIDE a
    signal. Runs that do not have signal on both sides (quieter side below
    -70 dBFS: digital silence, start or end of a sound) are skipped unless include_silence. min_len defaults to 0.2 ms.
    Event: kind, start, length, value, time_s, (block_offset)."""
    x = np.asarray(x, dtype=np.float64)
    if min_len is None:
        min_len = max(8, int(sr * 0.0002))
    ctx = max(int(sr * 0.005), 16)
    sil = 10.0 ** (SILENCE_DB / 20.0)
    events = []
    st, ln = _runs(x == 0.0)
    for s, L in zip(st, ln):
        if L < min_len:
            continue
        s, L = int(s), int(L)
        if not include_silence and _context_rms(x, s, s + L, ctx) < sil:
            continue
        events.append({"kind": "zero", "start": s, "length": L, "value": 0.0})
    same = np.diff(x) == 0.0
    st, ln = _runs(same)
    for s, L in zip(st, ln):
        L = int(L) + 1                       # n equal diffs = n+1 equal samples
        s = int(s)
        v = float(x[s])
        if L < min_len or v == 0.0 or abs(v) >= CLIP_THRESHOLD:
            continue
        if not include_silence and _context_rms(x, s, s + L, ctx) < sil:
            continue
        events.append({"kind": "repeat", "start": s, "length": L, "value": v})
    events.sort(key=lambda e: e["start"])
    for e in events:
        e["time_s"] = e["start"] / float(sr)
        if block_size:
            e["block_offset"] = int((e["start"] - first_block_start) % block_size)
    return events


def detect_clipping(x, threshold=CLIP_THRESHOLD, min_run=2):
    """Samples at or beyond +/- `threshold` of full scale. Returns n_samples,
    fraction, peak, n_runs (runs of >= min_run equal-sign samples), max_run and
    `runs`: list of {start, length, sign}."""
    x = np.asarray(x, dtype=np.float64)
    hit = np.abs(x) >= threshold
    out = {"n_samples": int(hit.sum()),
           "fraction": float(hit.mean()) if x.size else 0.0,
           "peak": float(np.max(np.abs(x))) if x.size else 0.0,
           "runs": [], "n_runs": 0, "max_run": 0}
    for sign in (1, -1):
        st, ln = _runs(hit & ((x > 0) if sign > 0 else (x < 0)))
        for s, L in zip(st, ln):
            if L >= min_run:
                out["runs"].append({"start": int(s), "length": int(L), "sign": sign})
    out["runs"].sort(key=lambda r: r["start"])
    out["n_runs"] = len(out["runs"])
    out["max_run"] = max((r["length"] for r in out["runs"]), default=0)
    return out


# ----------------------------------------------------------------------------
# DC, noise floor, hum
# ----------------------------------------------------------------------------
def dc_and_noise_floor(x, sr, frame_ms=20.0, quiet_percentile=10.0):
    """DC offset (mean of the whole file) and noise floor, all in dBFS.
    The noise floor is the RMS (DC removed per 20 ms frame) of the quietest
    10 percent of frames, digital silence excluded; it is only meaningful when
    the recording has quiet parts (bias for stationary noise is below 0.5 dB).
    Returns dc, dc_dbfs, noise_floor_dbfs, rms_dbfs, peak_dbfs,
    digital_silence_fraction, frames_used, quiet_parts (False = no pauses, so the
    floor is not a noise measurement)."""
    x = np.asarray(x, dtype=np.float64)
    fr = max(int(sr * frame_ms / 1000.0), 16)
    n = len(x) // fr
    dc = float(x.mean()) if x.size else 0.0
    out = {"dc": dc, "dc_dbfs": _db(abs(dc)),
           "rms_dbfs": _db(math.sqrt(float(np.mean(x ** 2))) if x.size else 0.0),
           "peak_dbfs": _db(float(np.max(np.abs(x))) if x.size else 0.0),
           "noise_floor_dbfs": None, "digital_silence_fraction": 0.0, "frames_used": 0,
           "quiet_parts": False}
    if n == 0:
        return out
    X = x[:n * fr].reshape(n, fr)
    Xc = X - X.mean(axis=1, keepdims=True)
    rms = np.sqrt((Xc ** 2).mean(axis=1))
    digital = np.abs(X).max(axis=1) == 0.0
    out["digital_silence_fraction"] = float(digital.mean())
    live = rms[~digital]
    if live.size:
        thr = np.percentile(live, quiet_percentile)
        q = live[live <= thr]
        out["noise_floor_dbfs"] = _db(math.sqrt(float(np.mean(q ** 2))))
        out["frames_used"] = int(q.size)
        # False when the quietest frames are about as loud as the rest (a steady tone,
        # or a capture with no pauses): the "floor" is then the signal, not the noise.
        out["quiet_parts"] = bool(out["noise_floor_dbfs"] < out["rms_dbfs"] - 10.0)
    return out


def hum_peaks(x, sr, prominence_db=12.0, max_harmonic=8):
    """Look for mains hum: peaks at harmonics of 50 Hz and of 60 Hz.
    Welch spectrum with up to 0.5 Hz resolution (needs >= 1 s of audio). A
    peak counts when it is `prominence_db` above the median of the spectrum
    within +/-20 Hz. Returns {"peaks": [{freq, base, harmonic, level_dbfs,
    prominence_db}], "mains_hz": 50 | 60 | None, "n_distinct": int,
    "strongest_dbfs": float | None}. mains_hz needs at least 2 harmonics that
    are NOT shared by both families (multiples of 300 Hz belong to both)."""
    x = np.asarray(x, dtype=np.float64)
    out = {"peaks": [], "mains_hz": None, "n_distinct": 0, "strongest_dbfs": None}
    if len(x) < sr:
        return out
    nper = int(min(len(x), 2 * sr))
    f, p = _sig.welch(x, fs=sr, window="hann", nperseg=nper, noverlap=nper // 2,
                      scaling="spectrum", detrend="constant")
    df = f[1] - f[0]
    pdb = 10.0 * np.log10(2.0 * p + 1e-20)      # amplitude of a sine, dBFS
    peaks = {}
    for base in (50.0, 60.0):
        for h in range(1, max_harmonic + 1):
            fc = base * h
            if fc > 0.45 * sr:
                break
            lo, hi = int(round((fc - 1.0) / df)), int(round((fc + 1.0) / df))
            if hi >= len(f):
                break
            k = lo + int(np.argmax(pdb[lo:hi + 1]))
            wlo, whi = max(int(round((f[k] - 20.0) / df)), 0), min(int(round((f[k] + 20.0) / df)), len(f) - 1)
            skip = max(int(round(1.5 / df)), 1)
            nb = np.concatenate((pdb[wlo:max(k - skip, wlo)], pdb[k + skip + 1:whi + 1]))
            if nb.size == 0:
                continue
            prom = float(pdb[k] - np.median(nb))
            if prom >= prominence_db:
                peaks[(base, h)] = {"freq": float(f[k]), "base": int(base), "harmonic": h,
                                    "level_dbfs": float(pdb[k]), "prominence_db": prom}
    out["peaks"] = sorted(peaks.values(), key=lambda d: d["freq"])
    cand = {}
    for base in (50, 60):
        distinct = [d for d in out["peaks"] if d["base"] == base and
                    min(d["freq"] % 300.0, 300.0 - d["freq"] % 300.0) > 2.0]
        cand[base] = (len(distinct), max((d["level_dbfs"] for d in distinct), default=-200.0))
    best = max(cand, key=lambda b: cand[b])
    if cand[best][0] >= 2:
        out["mains_hz"] = best
        out["n_distinct"] = cand[best][0]
    if out["peaks"]:
        out["strongest_dbfs"] = max(d["level_dbfs"] for d in out["peaks"])
    return out


# ----------------------------------------------------------------------------
# Block alignment and block-table correlation
# ----------------------------------------------------------------------------
def block_alignment(event_samples, block_size, first_block_start=0, alpha=1e-3):
    """Do events sit at one fixed position inside the audio block?
    Circular statistics on (sample - first_block_start) mod block_size:
    R = mean resultant length (0 = spread evenly, 1 = all at one offset) and
    the Rayleigh p-value. `clustered` needs >= 5 events, p < alpha and R > 0.5.
    `at_block_start` = clustered and the preferred offset is within a few
    samples of 0. Returns n, block_size, R, p_value, preferred_offset,
    fraction_within_tol, tol, clustered, at_block_start."""
    ev = np.asarray(list(event_samples), dtype=np.float64)
    n = int(ev.size)
    out = {"n": n, "block_size": int(block_size), "R": 0.0, "p_value": 1.0,
           "preferred_offset": None, "fraction_within_tol": 0.0,
           "tol": max(2, int(block_size) // 32), "clustered": False, "at_block_start": False}
    if n == 0 or not block_size:
        return out
    off = np.mod(ev - first_block_start, block_size)
    ang = 2.0 * np.pi * off / float(block_size)
    c, s = np.mean(np.cos(ang)), np.mean(np.sin(ang))
    R = float(math.hypot(c, s))
    pref = (math.atan2(s, c) % (2.0 * np.pi)) * block_size / (2.0 * np.pi)
    Rn = n * R                                   # resultant length (Zar's Rayleigh approximation)
    p = math.exp(math.sqrt(1.0 + 4.0 * n + 4.0 * (n * n - Rn * Rn)) - (1.0 + 2.0 * n)) if n > 1 else 1.0
    p = min(max(p, 0.0), 1.0)
    d = np.abs(((off - pref + block_size / 2.0) % block_size) - block_size / 2.0)
    out.update(R=R, p_value=p, preferred_offset=float(pref),
               fraction_within_tol=float(np.mean(d <= out["tol"])))
    out["clustered"] = bool(n >= 5 and p < alpha and R > 0.5)
    near0 = min(pref, block_size - pref) <= out["tol"]
    out["at_block_start"] = bool(out["clustered"] and near0)
    return out


def _normalize_blocks(blocks_table, sr=None, block_size=None):
    """blocks_table -> dict of numpy arrays: start, frames, late, status, gap."""
    t = blocks_table
    if t is None:
        return None
    if isinstance(t, np.ndarray) and t.dtype.names:
        d = {k: np.asarray(t[k]) for k in t.dtype.names}
    elif isinstance(t, (list, tuple)):
        keys = set()
        for r in t:
            keys.update(r.keys())
        d = {k: np.asarray([r.get(k, 0) for r in t]) for k in keys}
    else:
        d = {k: np.asarray(v) for k, v in dict(t).items()}
    n = 0
    for v in d.values():
        n = max(n, len(v))
    if n == 0:
        return None
    frames = np.asarray(d["frames"], dtype=np.float64) if "frames" in d else (
        np.full(n, float(block_size)) if block_size else None)
    if "start" in d:
        start = np.asarray(d["start"], dtype=np.int64)
    elif frames is not None:
        start = np.concatenate(([0], np.cumsum(frames[:-1]))).astype(np.int64)
    else:
        raise ValueError("blocks_table needs start, frames or a block_size argument")
    if frames is None:
        frames = np.diff(np.concatenate((start, [start[-1] + (np.median(np.diff(start)) if n > 1 else 0)]))).astype(np.float64)
    if "late" in d:
        late = np.asarray(d["late"]).astype(bool)
    elif "cb_ms" in d and sr:
        late = np.asarray(d["cb_ms"], dtype=np.float64) > frames / float(sr) * 1000.0
    else:
        late = np.zeros(n, bool)
    status = np.asarray(d["status"]).astype(np.int64) != 0 if "status" in d else np.zeros(n, bool)
    gap = np.zeros(n, bool)
    if "adc_time" in d and sr and n > 1:
        t_adc = np.asarray(d["adc_time"], dtype=np.float64)
        dt = np.diff(t_adc)
        expect = frames[:-1] / float(sr)
        gap[1:] = dt > 1.5 * expect
    return {"start": start, "frames": frames, "late": late, "status": status, "gap": gap, "n": n}


def _dilate(a, r=1):
    out = a.copy()
    for k in range(1, r + 1):
        out[k:] |= a[:-k]
        out[:-k] |= a[k:]
    return out


def correlate_with_blocks(events, blocks_table, sr=None, block_size=None, tolerance_blocks=1):
    """Do events (sample positions, or event dicts with `start`) sit in or next
    to blocks that were late (cb_ms > block time, or `late`), carried a
    PortAudio status flag, or follow a gap in ADC time? Compared with the share
    of blocks that are 'near a problem' anyway (binomial test).
    Returns n_blocks, n_late, n_status, n_gap, n_events, near_late,
    near_status, near_gap, near_any, fraction_near_any, chance_fraction,
    p_value, linked. `linked` needs >= 3 events, near_any >= 3 and p < 0.01."""
    tb = _normalize_blocks(blocks_table, sr, block_size)
    ev = np.asarray([e["start"] if isinstance(e, dict) else e for e in events], dtype=np.int64)
    if tb is None:
        return None
    n = tb["n"]
    out = {"n_blocks": int(n), "n_late": int(tb["late"].sum()), "n_status": int(tb["status"].sum()),
           "n_gap": int(tb["gap"].sum()), "n_events": int(ev.size), "near_late": 0, "near_status": 0,
           "near_gap": 0, "near_any": 0, "fraction_near_any": 0.0, "chance_fraction": 0.0,
           "p_value": 1.0, "linked": False}
    prob = tb["late"] | tb["status"] | tb["gap"]
    near = _dilate(prob, tolerance_blocks)
    out["chance_fraction"] = float(near.mean())
    if ev.size == 0:
        return out
    bi = np.clip(np.searchsorted(tb["start"], ev, side="right") - 1, 0, n - 1)
    out["near_late"] = int(_dilate(tb["late"], tolerance_blocks)[bi].sum())
    out["near_status"] = int(_dilate(tb["status"], tolerance_blocks)[bi].sum())
    out["near_gap"] = int(_dilate(tb["gap"], tolerance_blocks)[bi].sum())
    k = int(near[bi].sum())
    out["near_any"] = k
    out["fraction_near_any"] = k / float(ev.size)
    chance = min(max(out["chance_fraction"], 1e-6), 1.0 - 1e-6)
    out["p_value"] = float(_stats.binom.sf(k - 1, ev.size, chance)) if k > 0 else 1.0
    out["linked"] = bool(ev.size >= MIN_EVENTS and k >= 3 and out["p_value"] < 0.01)
    return out


# ----------------------------------------------------------------------------
# Whole-recording report
# ----------------------------------------------------------------------------
def _match(a, b, max_lag):
    """How many of events `a` have an event of `b` within max_lag samples."""
    if not a:
        return 0
    bs = np.sort(np.asarray(b, dtype=np.int64)) if b else np.zeros(0, np.int64)
    n = 0
    for s in a:
        if bs.size:
            i = int(np.searchsorted(bs, s))
            c = []
            if i < bs.size:
                c.append(abs(int(bs[i]) - s))
            if i > 0:
                c.append(abs(int(bs[i - 1]) - s))
            if c and min(c) <= max_lag:
                n += 1
    return n


def _single_report(x, sr, block_size, blocks_table):
    x = np.asarray(x, dtype=np.float64)
    dur = len(x) / float(sr)
    clicks = detect_clicks(x, sr, block_size=block_size)
    drops = detect_dropouts(x, sr, block_size=block_size)
    near = max(MERGE_GAP, 8)
    dstarts = [d["start"] for d in drops]
    ends = [d["start"] + d["length"] for d in drops]
    for c in clicks:
        c["in_dropout"] = any((ds - near <= c["start"] <= de + near) for ds, de in zip(dstarts, ends))
    free = [c for c in clicks if not c["in_dropout"]]
    positions = [c["start"] for c in free] + dstarts
    rep = {
        "sr": int(sr), "n_samples": int(len(x)), "duration_s": dur, "block_size": block_size,
        "clicks": clicks, "n_clicks": len(free),
        "clicks_per_min": (len(free) / dur * 60.0) if dur > 0 else 0.0,
        "dropouts": drops, "n_dropouts": len(drops),
        "clipping": detect_clipping(x),
        "dc_noise": dc_and_noise_floor(x, sr),
        "hum": hum_peaks(x, sr),
        "alignment": block_alignment(positions, block_size) if block_size and positions else None,
        "blocks": correlate_with_blocks(positions, blocks_table, sr=sr, block_size=block_size)
        if blocks_table is not None else None,
    }
    return rep


def analyze(x, sr, block_size=None, blocks_table=None, meta=None, raw=None, max_lag_ms=5.0):
    """Run every detector and return one report dict for verdict().

    meta (all optional, None = unknown): source ('raw' | 'processed' |
    'unknown'), effects_off, monitoring_off, silent_input (nothing was being
    played or sung into the input). raw = the raw sound-card capture made at
    the same time as `x` (processed track): its clicks are compared with the
    clicks of `x`, matched within +/- max_lag_ms."""
    rep = _single_report(x, sr, block_size, blocks_table)
    rep["meta"] = dict(meta or {})
    rep["raw"] = None
    rep["compare"] = None
    if raw is not None:
        r = _single_report(raw, sr, block_size, None)
        lag = int(sr * max_lag_ms / 1000.0)
        p = [c["start"] for c in rep["clicks"] if not c["in_dropout"]]
        q = [c["start"] for c in r["clicks"] if not c["in_dropout"]]
        shared = _match(p, q, lag)
        rep["raw"] = r
        rep["compare"] = {"processed": len(p), "raw": len(q), "shared": shared,
                          "processed_only": len(p) - shared,
                          "fraction_processed_only": (len(p) - shared) / float(len(p)) if p else 0.0,
                          "max_lag_samples": lag}
    return rep


# ----------------------------------------------------------------------------
# Verdict
# ----------------------------------------------------------------------------
_CONF = {0: "low", 1: "low", 2: "low", 3: "medium"}   # 4 and more = high


def _conf(score):
    return "high" if score >= 4 else _CONF.get(score, "low")


_RANK = {"high": 3, "medium": 2, "low": 1}

NEXT_TEST = {
    "software_scheduling": (
        "Record the same 60 s again with a larger block (256, then 512) in the same driver mode, "
        "and with the Windows power plan on High performance. If the clicks and late blocks "
        "disappear or drop sharply, scheduling is the cause."),
    "hardware_or_driver_input": (
        "Record 60 s of the RAW input with effects and monitoring off and nothing playing, then "
        "repeat with another USB port / cable and in another driver (WASAPI exclusive, ASIO). "
        "Clicks at the same rate in every engine mode point at the interface or its driver."),
    "software_dsp": (
        "Record the raw tap and the processed track together, then switch the effects off one at a "
        "time (CLEAN INPUT first, then each track effect) until the clicks vanish from the "
        "processed track."),
    "gain_staging": (
        "Lower the interface input gain until the loudest passage peaks around -6 dBFS, "
        "re-record, and check that no run of full-scale samples remains."),
    "electrical": (
        "Run the interface from a different USB port or a powered hub, unplug other devices "
        "(laptop charger, monitors), use balanced cables, and record 30 s of silence again. "
        "Note whether the hum level or the DC offset changes."),
    "split_handoff": (
        "The silent blocks are made inside the Split in/out hand-off (the output found no input block "
        "ready), not by the sound card. A bigger block does NOT fix that. Read logs/split_timing_*.csv "
        "(unmount the engine to save it) and send it with looper.log; or record the same test in "
        "Shared mode to confirm."),
    "clean": (
        "If you still hear crackle, record it while it is audible, note the time, and run the same "
        "analysis on the raw tap and on the processed track."),
}


def verdict(report):
    """Turn analyze() output into ranked hypotheses.
    Returns {"top": name, "confidence": ..., "hypotheses": [{name, confidence,
    score, evidence: [...], next_test}], "notes": [...], "summary": str,
    "disclaimer": str}. Names: software_scheduling, hardware_or_driver_input,
    software_dsp, gain_staging, electrical, split_handoff, or clean when nothing was found.
    These are hypotheses, never certainty."""
    meta = report.get("meta") or {}
    n_clk = int(report.get("n_clicks", 0))
    drops = report.get("dropouts") or []
    al = report.get("alignment")
    bl = report.get("blocks")
    cmp_ = report.get("compare")
    clip = report.get("clipping") or {}
    hum = report.get("hum") or {}
    dcn = report.get("dc_noise") or {}
    dur = report.get("duration_s", 0.0)
    rate = report.get("clicks_per_min", 0.0)
    block = report.get("block_size")
    hyps = []
    notes = []

    n_ev = n_clk + len(drops)
    has_events = n_ev >= MIN_EVENTS
    clustered = bool(al and al.get("clustered"))
    at_start = bool(al and al.get("at_block_start"))
    linked = bool(bl and bl.get("linked"))
    late_any = bool(bl and (bl["n_late"] or bl["n_status"] or bl["n_gap"]))

    if bl and late_any:
        notes.append("%d late block(s), %d with PortAudio status flags, %d ADC-time gap(s) in %d blocks."
                     % (bl["n_late"], bl["n_status"], bl["n_gap"], bl["n_blocks"]))
    if dcn.get("noise_floor_dbfs") is not None and dcn["noise_floor_dbfs"] > -60.0 and \
            (dcn.get("quiet_parts") or meta.get("silent_input")):
        notes.append("Noise floor is high: %.1f dBFS (a quiet interface is below -70)." % dcn["noise_floor_dbfs"])

    # ---- software scheduling -------------------------------------------- #
    if has_events and (clustered or linked):
        ev, sc = [], 0
        if at_start:
            sc += 3
            ev.append("%d of %d events sit at the start of the %d-sample block (offset %.0f, R=%.2f, p=%.2g)."
                      % (round(al["fraction_within_tol"] * al["n"]), al["n"], block,
                         al["preferred_offset"], al["R"], al["p_value"]))
        elif clustered:
            sc += 2
            ev.append("Events cluster at block offset %.0f of %d (R=%.2f, p=%.2g), not at random."
                      % (al["preferred_offset"], block, al["R"], al["p_value"]))
        if linked:
            sc += 3
            ev.append("%d of %d events are in or next to a late block, status-flag block or ADC-time gap "
                      "(chance level %.1f%%, p=%.2g)." % (bl["near_any"], bl["n_events"],
                                                          bl["chance_fraction"] * 100.0, bl["p_value"]))
        if bl and bl["n_status"]:
            sc += 1
            ev.append("PortAudio reported status flags on %d block(s)." % bl["n_status"])
        mult = [d for d in drops if block and d["length"] >= block * 0.9 and
                min(d["length"] % block, block - d["length"] % block) <= max(2, block // 16)]
        if mult:
            sc += 1
            ev.append("%d dropout(s) are a whole number of blocks long." % len(mult))
        hyps.append(("software_scheduling", sc, ev))

    # ---- hardware / driver input ---------------------------------------- #
    if n_clk >= MIN_EVENTS and not clustered and not linked:
        sc, ev = 1, ["%d click(s), %.1f per minute, at random positions inside the block "
                     "(no fixed offset)." % (n_clk, rate)]
        quiet_cap = bool(meta.get("silent_input")) or (meta.get("effects_off") is True and
                                                         meta.get("monitoring_off") is True)
        if quiet_cap:
            sc += 1
            ev.append("The capture was made with nothing playing / effects and monitoring off, so the "
                      "clicks were not produced by the program's own sound.")
        elif meta.get("effects_off") is False:
            ev.append("Effects were on: the clicks could also come from the DSP (record the raw tap).")
        if bl and not late_any:
            sc += 1
            ev.append("No late block, status flag or ADC-time gap in %d blocks." % bl["n_blocks"])
        elif bl is None:
            ev.append("No block timing table given: scheduling cannot be ruled out.")
        if meta.get("source") == "raw" or (cmp_ and cmp_["raw"] >= MIN_EVENTS and cmp_["shared"] >= MIN_EVENTS):
            sc += 1
            ev.append("The clicks are present in the raw sound-card capture, before any DSP.")
        if cmp_ and cmp_["fraction_processed_only"] >= 0.7 and cmp_["processed_only"] >= MIN_EVENTS:
            sc = 0                               # the DSP rule below explains them
        if sc:
            hyps.append(("hardware_or_driver_input", sc, ev))

    # ---- DSP ------------------------------------------------------------- #
    if cmp_ and cmp_["processed_only"] >= MIN_EVENTS and cmp_["fraction_processed_only"] >= 0.7:
        sc = 3
        ev = ["%d of %d clicks in the processed track have no click in the raw capture (within %d samples)."
              % (cmp_["processed_only"], cmp_["processed"], cmp_["max_lag_samples"]),
              "The raw capture has %d click(s)." % cmp_["raw"]]
        if cmp_["processed_only"] >= 10 and cmp_["fraction_processed_only"] >= 0.9:
            sc += 1
        hyps.append(("software_dsp", sc, ev))
    elif n_clk >= MIN_EVENTS and cmp_ is None and meta.get("source") == "processed" and \
            meta.get("effects_off") is False and not clustered and not linked:
        hyps.append(("software_dsp", 1, [
            "%d click(s) in a processed track with effects on, and no raw capture to compare." % n_clk]))

    # ---- gain staging ---------------------------------------------------- #
    if clip.get("n_runs", 0) >= 1:
        sc = 4 if (clip["n_runs"] >= 3 or clip["max_run"] >= 8) else 3
        hyps.append(("gain_staging", sc, [
            "%d run(s) of samples held at full scale, longest %d samples, %d samples in total "
            "(%.3f %% of the file)." % (clip["n_runs"], clip["max_run"], clip["n_samples"],
                                        clip["fraction"] * 100.0)]))
    elif clip.get("n_samples", 0) >= 1:
        hyps.append(("gain_staging", 1, ["%d isolated sample(s) at full scale (peak %.3f)."
                                         % (clip["n_samples"], clip["peak"])]))

    # ---- electrical ------------------------------------------------------ #
    ev, sc = [], 0
    if hum.get("mains_hz"):
        sc = 4 if (hum.get("strongest_dbfs") or -200.0) >= -50.0 else 3
        ev.append("%d Hz hum with %d distinct harmonic(s), strongest %.1f dBFS."
                  % (hum["mains_hz"], hum["n_distinct"], hum["strongest_dbfs"]))
    if dcn and dcn.get("dc_dbfs", -200.0) >= -50.0:
        sc = max(sc, 4 if dcn["dc_dbfs"] >= -40.0 else 3)
        ev.append("DC offset %.4f (%.1f dBFS)." % (dcn["dc"], dcn["dc_dbfs"]))
    if sc:
        hyps.append(("electrical", sc, ev))

    # ---- split in/out hand-off ------------------------------------------ #
    su, so = int(meta.get("split_underflows") or 0), int(meta.get("split_out_blocks") or 0)
    if meta.get("split") and su > 0:
        frac = su / float(so) if so else 1.0
        if frac >= 0.005 or su >= 20:
            hyps.append(("split_handoff", 5, [
                "Split in/out mode: %d of %d output blocks (%.1f %%) found no input block ready and played "
                "silence (SplitStream underflow counter)." % (su, so, frac * 100.0)]))
        else:
            notes.append("Split in/out mode: %d underflow(s) in %d output blocks." % (su, so))
    split_hit = any(h[0] == "split_handoff" for h in hyps)

    out_h = []
    for name, sc, ev in hyps:
        c = _conf(sc)
        out_h.append({"name": name, "confidence": c, "score": sc, "evidence": ev,
                      "next_test": NEXT_TEST["split_handoff"] if (split_hit and name == "software_scheduling")
                      else NEXT_TEST[name]})
    out_h.sort(key=lambda h: (-_RANK[h["confidence"]], -h["score"]))

    if not out_h:
        ev = ["%d click(s) (%.1f per minute), %d dropout(s), %d clipped run(s) in %.1f s."
              % (n_clk, rate, len(drops), clip.get("n_runs", 0), dur)]
        if n_ev and not has_events:
            ev.append("Fewer than %d events: too few for any verdict." % MIN_EVENTS)
        out_h.append({"name": "clean", "confidence": "high" if dur >= 5.0 else "medium", "score": 0,
                      "evidence": ev, "next_test": NEXT_TEST["clean"]})
    top = out_h[0]
    summary = "Most likely: %s (confidence %s). %s" % (top["name"], top["confidence"], top["evidence"][0])
    return {"top": top["name"], "confidence": top["confidence"], "hypotheses": out_h,
            "notes": notes, "summary": summary, "disclaimer": DISCLAIMER}
