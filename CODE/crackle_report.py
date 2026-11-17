"""
crackle_report.py  (Live Looper Pro v2.0, Phase 10 Crackle Lab, T019)

Turns a capture (a T020 capture folder or a plain WAV / FLAC) into an analysis
pack that a person or Claude can read: verdict, evidence, per-millisecond
numbers, a list of events, pictures and short audio excerpts. It only CALLS
crackle_core (never changes it). No Tk, no sounddevice, no engine import.
matplotlib is optional: without it the PNG files are skipped and the report says so.

    from crackle_report import run
    result = run("captures/20261111_153000_test")            # folder from T020
    result = run("take.wav", block_size=64)                  # plain file
    result = run(compare=("raw.wav", "processed.wav"))       # DSP-made or input clicks?

Command line: `python3 tools/analyze_audio.py <folder or file> [options]`.

Files written to the output folder (the pack is what you attach to a Claude chat):
  report.md        verdict, evidence, next test, numbers (under 150 lines)
  report.json      the same facts for programs (stable: no time stamps, no paths)
  ms.csv.gz        one row per millisecond of audio, columns MS_COLUMNS
  events.csv       one row per click / dropout / clipped run, columns EVENT_COLUMNS
  report.png       waveform with event marks, spectrogram, histogram of the offset inside the block
  event_01.png ... the worst 10 events, +/- 20 ms, waveform and spectrogram
  excerpts/*.wav   +/- 1 s of audio around the worst events (24-bit)
  analysis_pack.zip  all of the above except the raw capture (which stays the truth)

ms.csv.gz columns: t_ms, peak, rms, dc, max_step, zero_crossings, hf_ratio,
centroid_hz, dominant_hz, band0_db .. band7_db (edges in report.json), clip_count,
flags. One row = round(sr/1000) samples (exactly 1 ms at 48000 Hz). flags is a bit
set: 1 click, 2 dropout, 4 clipped run, 8 late block, 16 PortAudio status flag,
32 ADC-time gap. When the pack would be larger than --max-mb the file keeps every
2nd, 5th or 10th row (peak, max_step, clip_count and flags are combined over the
group so that no event is lost) and the report says so.

events.csv columns: type (click, dropout_zero, dropout_repeat, clip), start_sample,
t_ms, amplitude, width_samples, hf_db, block_index, offset_in_block,
nearest_engine_event_ms (distance to the closest late / status-flag / ADC-gap block,
empty without blocks.csv.gz), confidence (low, medium, high).
"""
import gzip
import json
import math
import os
import shutil
import zipfile

import numpy as np

import crackle_core as cc

REPORT_VERSION = 1
FLAG_CLICK, FLAG_DROPOUT, FLAG_CLIP, FLAG_LATE, FLAG_STATUS, FLAG_GAP = 1, 2, 4, 8, 16, 32

MS_COLUMNS = (["t_ms", "peak", "rms", "dc", "max_step", "zero_crossings", "hf_ratio",
               "centroid_hz", "dominant_hz"] + ["band%d_db" % i for i in range(8)] +
              ["clip_count", "flags"])
EVENT_COLUMNS = ["type", "start_sample", "t_ms", "amplitude", "width_samples", "hf_db",
                 "block_index", "offset_in_block", "nearest_engine_event_ms", "confidence"]
REPORT_KEYS = ["version", "tool", "input", "meta", "verdict", "counts", "dc_noise", "hum",
               "clipping", "alignment", "blocks", "compare", "worst_events", "band_edges_hz",
               "pack", "notes"]
MS_DECIMATIONS = (1, 2, 5, 10)
MAX_MD_LINES = 150
_ZIP_TIME = (2000, 1, 1, 0, 0, 0)


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def read_blocks_csv(path):
    """blocks.csv.gz (T020) -> dict of numpy arrays (nan stays nan), or None."""
    with gzip.open(path, "rt") as fh:
        head = fh.readline().strip()
        if not head:
            return None
        names = head.split(",")
        data = np.genfromtxt(fh, delimiter=",", ndmin=2)
    if data.size == 0:
        return None
    data = np.atleast_2d(data)
    return {n: data[:, i] for i, n in enumerate(names) if i < data.shape[1]}


def _read_audio(path, channel):
    import soundfile as sf
    data, sr = sf.read(str(path), dtype="float64", always_2d=True)
    ch = min(max(int(channel), 0), data.shape[1] - 1)
    return np.ascontiguousarray(data[:, ch]), int(sr), int(data.shape[1]), ch


def load_capture(path, channel=0):
    """A capture folder (raw.wav [+ blocks.csv.gz, meta.json]) or one WAV / FLAC file.
    Returns dict: kind ('folder' | 'file'), name, x, sr, channels, channel,
    blocks (dict or None), meta (dict), block_size (int or None)."""
    path = str(path)
    blocks, meta = None, {}
    if os.path.isdir(path):
        audio = None
        for nm in ("raw.wav", "raw.flac"):
            if os.path.isfile(os.path.join(path, nm)):
                audio = os.path.join(path, nm)
                break
        if audio is None:
            raise FileNotFoundError("no raw.wav in capture folder %s" % path)
        kind = "folder"
        b = os.path.join(path, "blocks.csv.gz")
        if os.path.isfile(b):
            blocks = read_blocks_csv(b)
        m = os.path.join(path, "meta.json")
        if os.path.isfile(m):
            with open(m, encoding="utf-8") as fh:
                meta = json.load(fh)
        name = os.path.basename(os.path.normpath(path))
    else:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        audio, kind, name = path, "file", os.path.basename(path)
    x, sr, nch, ch = _read_audio(audio, channel)
    bs = meta.get("block_size")
    return {"kind": kind, "name": name, "x": x, "sr": sr, "channels": nch, "channel": ch,
            "blocks": blocks, "meta": meta, "block_size": int(bs) if bs else None}


# ----------------------------------------------------------------------------
# Events and per-millisecond table
# ----------------------------------------------------------------------------
def _click_confidence(score):
    return "high" if score >= 40.0 else ("medium" if score >= 20.0 else "low")


def build_events(rep, sr, blocks_table=None, block_size=None):
    """All events of an analyze() report as a list of dicts (EVENT_COLUMNS plus
    `rank`), sorted by start. Clicks that sit inside a dropout are left out
    (the dropout carries them)."""
    tb = cc._normalize_blocks(blocks_table, sr, block_size) if blocks_table is not None else None
    prob_starts = None
    if tb is not None:
        prob = tb["late"] | tb["status"] | tb["gap"]
        prob_starts = np.sort(tb["start"][prob]) if prob.any() else np.zeros(0, np.int64)

    def where(s, core_offset):
        bi, off, near = "", core_offset if core_offset is not None else "", ""
        if tb is not None:
            i = int(np.clip(np.searchsorted(tb["start"], s, side="right") - 1, 0, tb["n"] - 1))
            bi, off = i, int(s - tb["start"][i])
            if prob_starts is not None and prob_starts.size:
                j = int(np.searchsorted(prob_starts, s))
                c = [abs(int(prob_starts[k]) - s) for k in (j - 1, j) if 0 <= k < prob_starts.size]
                near = round(min(c) / float(sr) * 1000.0, 3)
        return bi, off, near

    ev = []
    for c in rep["clicks"]:
        if c.get("in_dropout"):
            continue
        bi, off, near = where(c["start"], c.get("block_offset"))
        ev.append({"type": "click", "start_sample": c["start"], "t_ms": c["start"] / sr * 1000.0,
                   "amplitude": c["amplitude"], "width_samples": c["width"], "hf_db": c["hf_db"],
                   "block_index": bi, "offset_in_block": off, "nearest_engine_event_ms": near,
                   "confidence": _click_confidence(c["score"]), "rank": (0, -c["score"])})
    for d in rep["dropouts"]:
        bi, off, near = where(d["start"], d.get("block_offset"))
        ev.append({"type": "dropout_" + d["kind"], "start_sample": d["start"],
                   "t_ms": d["start"] / sr * 1000.0, "amplitude": abs(d["value"]),
                   "width_samples": d["length"], "hf_db": "", "block_index": bi,
                   "offset_in_block": off, "nearest_engine_event_ms": near,
                   "confidence": "high", "rank": (1, -d["length"])})
    for r in rep["clipping"].get("runs", []):
        bi, off, near = where(r["start"], None)
        ev.append({"type": "clip", "start_sample": r["start"], "t_ms": r["start"] / sr * 1000.0,
                   "amplitude": 1.0, "width_samples": r["length"], "hf_db": "", "block_index": bi,
                   "offset_in_block": off, "nearest_engine_event_ms": near,
                   "confidence": "high", "rank": (2, -r["length"])})
    ev.sort(key=lambda e: e["start_sample"])
    return ev


def worst_events(events, n=10):
    return sorted(events, key=lambda e: (e["rank"], e["start_sample"]))[:n]


def ms_flags(nrows, frame, sr, events, blocks_table, block_size):
    """Bit flags per millisecond row (see module docstring)."""
    fl = np.zeros(nrows, dtype=np.int64)
    if nrows == 0:
        return fl

    def mark(start, length, bit):
        a = max(int(start) // frame, 0)
        b = min((int(start) + max(int(length), 1) - 1) // frame, nrows - 1)
        if a <= nrows - 1 and b >= a:
            fl[a:b + 1] |= bit

    for e in events:
        bit = FLAG_CLICK if e["type"] == "click" else (FLAG_CLIP if e["type"] == "clip" else FLAG_DROPOUT)
        mark(e["start_sample"], e["width_samples"], bit)
    if blocks_table is not None:
        tb = cc._normalize_blocks(blocks_table, sr, block_size)
        if tb is not None:
            for i in np.flatnonzero(tb["late"]):
                mark(tb["start"][i], tb["frames"][i], FLAG_LATE)
            for i in np.flatnonzero(tb["status"]):
                mark(tb["start"][i], tb["frames"][i], FLAG_STATUS)
            for i in np.flatnonzero(tb["gap"]):
                mark(tb["start"][i], tb["frames"][i], FLAG_GAP)
    return fl


def _gz_open(path):
    """(gzip writer, raw file). mtime=0 and no file name inside: the same input
    gives the same bytes."""
    raw = open(path, "wb")
    return gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0), raw


def write_ms_csv(path, feats, flags, every=1):
    """ms.csv.gz; `every` > 1 keeps every Nth row (events survive, see module docstring).
    Returns the number of rows written."""
    n = len(feats["peak"])
    idx = np.arange(0, n, every) if n else np.zeros(0, int)
    if every > 1 and n:
        peak = np.maximum.reduceat(feats["peak"], idx)
        step = np.maximum.reduceat(feats["max_step"], idx)
        clip = np.add.reduceat(feats["clip_count"], idx)
        fl = np.bitwise_or.reduceat(flags, idx)
    else:
        peak, step, clip, fl = feats["peak"], feats["max_step"], feats["clip_count"], flags
    t_ms = feats["time_s"][idx] * 1000.0 if n else np.zeros(0)
    band = feats["band_db"]
    gz, rawf = _gz_open(path)
    try:
        gz.write((",".join(MS_COLUMNS) + "\n").encode())
        out = []
        for k, i in enumerate(idx):
            out.append("%.3f,%.6g,%.6g,%.6g,%.6g,%d,%.4f,%.1f,%.1f,%s,%d,%d\n" % (
                t_ms[k], peak[k], feats["rms"][i], feats["dc"][i], step[k],
                feats["zero_crossings"][i], feats["hf_ratio"][i], feats["centroid_hz"][i],
                feats["dominant_hz"][i], ",".join("%.1f" % v for v in band[i]), clip[k], fl[k]))
            if len(out) >= 4096:
                gz.write("".join(out).encode())
                out = []
        if out:
            gz.write("".join(out).encode())
    finally:
        gz.close()
        rawf.close()
    return int(len(idx))


def write_events_csv(path, events):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(EVENT_COLUMNS) + "\n")
        for e in events:
            row = []
            for c in EVENT_COLUMNS:
                v = e[c]
                if isinstance(v, float):
                    v = "%.6g" % v if c != "t_ms" else "%.3f" % v
                row.append(str(v))
            fh.write(",".join(row) + "\n")


# ----------------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------------
def _clean(o):
    """numpy / nan safe copy for json (floats rounded to 6 decimals)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 6)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


def _strip_lists(rep):
    """Counts only: the long event lists live in events.csv."""
    r = {k: v for k, v in rep.items() if k not in ("clicks", "dropouts", "raw")}
    r["clipping"] = {k: v for k, v in rep["clipping"].items() if k != "runs"}
    return r


def build_report_dict(info, rep, verdict, events, pack, notes, meta):
    top = worst_events(events, 20)
    for e in top:
        pass
    wk = [{k: v for k, v in e.items() if k != "rank"} for e in top]
    stripped = _strip_lists(rep)
    counts = {"clicks": rep["n_clicks"], "clicks_per_min": rep["clicks_per_min"],
              "dropouts": rep["n_dropouts"], "clip_runs": rep["clipping"]["n_runs"],
              "events_total": len(events)}
    d = {
        "version": REPORT_VERSION,
        "tool": "crackle_report",
        "input": info,
        "meta": meta,
        "verdict": verdict,
        "counts": counts,
        "dc_noise": stripped.get("dc_noise"),
        "hum": stripped.get("hum"),
        "clipping": stripped["clipping"],
        "alignment": stripped.get("alignment"),
        "blocks": stripped.get("blocks"),
        "compare": rep.get("compare"),
        "worst_events": wk,
        "band_edges_hz": [v if math.isfinite(v) else None for v in cc.BAND_EDGES_HZ],
        "pack": pack,
        "notes": notes,
    }
    return _clean(d)


# ----------------------------------------------------------------------------
# report.md
# ----------------------------------------------------------------------------
def build_markdown(rj, events):
    v = rj["verdict"]
    hyp = v["hypotheses"][0]
    L = []
    L.append("# Verdict: %s (confidence %s)" % (v["top"], v["confidence"]))
    L.append("")
    L.append(v["summary"])
    L.append("")
    L.append("## Evidence")
    for e in hyp["evidence"][:8]:
        L.append("- " + e)
    for n in v.get("notes", [])[:4]:
        L.append("- Note: " + n)
    L.append("")
    L.append("## Next test")
    L.append(hyp["next_test"])
    L.append("")
    if len(v["hypotheses"]) > 1:
        L.append("## Other hypotheses")
        for h in v["hypotheses"][1:5]:
            L.append("- %s (%s): %s" % (h["name"], h["confidence"], h["evidence"][0]))
        L.append("")
    inp, c = rj["input"], rj["counts"]
    L.append("## Numbers")
    L.append("- Input: %s (%s), %.1f s at %d Hz, channel %d of %d, block size %s." % (
        inp["name"], inp["kind"], inp["duration_s"], inp["sr"], inp["channel"], inp["channels"],
        inp["block_size"] if inp["block_size"] else "unknown"))
    L.append("- Clicks: %d (%.1f per minute). Dropouts: %d. Clipped runs: %d." % (
        c["clicks"], c["clicks_per_min"], c["dropouts"], c["clip_runs"]))
    dn = rj.get("dc_noise") or {}
    if dn:
        nf = dn.get("noise_floor_dbfs")
        L.append("- DC offset %s (%s dBFS). Noise floor %s dBFS%s." % (
            _f(dn.get("dc")), _f(dn.get("dc_dbfs"), 1), _f(nf, 1),
            "" if dn.get("quiet_parts") else " (no quiet parts, not meaningful)"))
    hum = rj.get("hum") or {}
    if hum.get("mains_hz"):
        L.append("- Hum: %d Hz, %s distinct harmonic(s), strongest %s dBFS." % (
            hum["mains_hz"], hum.get("n_distinct"), _f(hum.get("strongest_dbfs"), 1)))
    al = rj.get("alignment")
    if al and al.get("n"):
        L.append("- Position in the block: %d events, preferred offset %s of %s, R=%s, p=%s, clustered=%s." % (
            al["n"], _f(al.get("preferred_offset"), 1), al["block_size"], _f(al["R"], 2),
            _f(al["p_value"], 4), "yes" if al["clustered"] else "no"))
    bl = rj.get("blocks")
    if bl:
        L.append("- Blocks: %d total, %d late, %d with status flags, %d ADC-time gaps; %d of %d events near one "
                 "(chance %.1f%%, p=%s)." % (bl["n_blocks"], bl["n_late"], bl["n_status"], bl["n_gap"],
                                             bl["near_any"], bl["n_events"], bl["chance_fraction"] * 100.0,
                                             _f(bl["p_value"], 4)))
    cm = rj.get("compare")
    if cm:
        L.append("- Compare: %d clicks in the processed track, %d in the raw capture, %d shared, "
                 "%d only in the processed track." % (cm["processed"], cm["raw"], cm["shared"],
                                                      cm["processed_only"]))
    L.append("")
    if rj["worst_events"]:
        L.append("## Worst events (full list in events.csv)")
        L.append("| # | type | t_ms | amplitude | width | block | offset | near engine event ms | conf |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for i, e in enumerate(rj["worst_events"][:10], 1):
            L.append("| %02d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                i, e["type"], _f(e["t_ms"], 1), _f(e["amplitude"], 3), e["width_samples"],
                _s(e["block_index"]), _s(e["offset_in_block"]), _s(e["nearest_engine_event_ms"]),
                e["confidence"]))
        L.append("")
    L.append("## Files")
    L.append("- events.csv: every event (%s)." % ", ".join(EVENT_COLUMNS))
    pk = rj["pack"]
    L.append("- ms.csv.gz: %d rows, one per %s ms of audio (column list in crackle_report.py docstring)." % (
        pk["ms_rows"], "1" if pk["ms_every"] == 1 else str(pk["ms_every"])))
    L.append("- report.png and event_NN.png (the worst 10 events, +/- 20 ms): %s." % pk["png"])
    L.append("- excerpts/event_NN.wav: +/- 1 s around the worst events (%d kept)." % pk["excerpts_kept"])
    L.append("- analysis_pack.zip: everything above, limit %s MB." % pk["max_mb"])
    L.append("")
    L.append("## Limits")
    for n in rj["notes"]:
        L.append("- " + n)
    L.append("- " + v["disclaimer"])
    if len(L) > MAX_MD_LINES - 1:
        L = L[:MAX_MD_LINES - 2] + ["- (report shortened, see report.json)"]
    return "\n".join(L) + "\n"


def _f(v, nd=4):
    return "n/a" if v is None else ("%.*f" % (nd, v))


def _s(v):
    return "" if v is None or v == "" else str(v)


# ----------------------------------------------------------------------------
# Pictures (matplotlib is optional)
# ----------------------------------------------------------------------------
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except Exception:
        return None


def make_pictures(out_dir, x, sr, events, block_size, worst):
    """report.png and event_NN.png. Returns "ok" or a one-line reason they were skipped."""
    plt = _plt()
    if plt is None:
        return "skipped (matplotlib is not installed)"
    try:
        _overview_png(plt, os.path.join(out_dir, "report.png"), x, sr, events, block_size)
        for i, e in enumerate(worst, 1):
            _event_png(plt, os.path.join(out_dir, "event_%02d.png" % i), x, sr, e, i)
    except Exception as exc:           # pictures must never stop the report
        return "skipped (%s: %s)" % (type(exc).__name__, exc)
    return "ok"


def _overview_png(plt, path, x, sr, events, block_size):
    from scipy import signal as sg
    fig, axs = plt.subplots(3, 1, figsize=(11, 9))
    n = len(x)
    ax = axs[0]
    cols = min(1500, max(n // 4, 1))
    per = max(n // cols, 1)
    m = (n // per) * per
    if m:
        seg = x[:m].reshape(-1, per)
        t = (np.arange(seg.shape[0]) * per + per / 2.0) / sr
        ax.fill_between(t, seg.min(axis=1), seg.max(axis=1), color="#4477aa", linewidth=0)
    ymax = max(float(np.max(np.abs(x))) if n else 1.0, 1e-3) * 1.15
    ax.set_ylim(-ymax, ymax)
    for typ, color, mk in (("click", "#cc3311", "v"), ("dropout", "#ee7733", "s"), ("clip", "#0077bb", "^")):
        ts = [e["start_sample"] / sr for e in events if e["type"].startswith(typ)]
        if ts:
            ax.plot(ts, [ymax * 0.93] * len(ts), mk, color=color, markersize=5, label="%s (%d)" % (typ, len(ts)))
    ax.set_title("Waveform with events")
    ax.set_xlabel("s")
    ax.legend(loc="upper right", fontsize=8)
    ax = axs[1]
    if n >= 2048:
        f, tt, S = sg.spectrogram(x, sr, nperseg=1024, noverlap=0)
        db = 10.0 * np.log10(S + 1e-14)
        ax.imshow(db, origin="lower", aspect="auto", extent=[tt[0], tt[-1], f[0], f[-1]],
                  vmin=db.max() - 100.0, vmax=db.max(), cmap="magma")
    ax.set_title("Spectrogram (dB)")
    ax.set_xlabel("s")
    ax.set_ylabel("Hz")
    ax = axs[2]
    offs = [e["offset_in_block"] for e in events if e["offset_in_block"] != "" and e["type"] != "clip"]
    if block_size and offs:
        ax.hist(offs, bins=min(int(block_size), 64), range=(0, block_size), color="#228833")
        ax.set_title("Where events fall inside the %d-sample audio block" % block_size)
        ax.set_xlabel("offset in block (samples)")
    else:
        ax.text(0.5, 0.5, "No events, or block size unknown", ha="center", va="center")
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def _event_png(plt, path, x, sr, e, number):
    half = int(0.02 * sr)
    s = int(e["start_sample"])
    a, b = max(s - half, 0), min(s + half, len(x))
    seg = x[a:b]
    t_ms = (np.arange(a, b) - s) / sr * 1000.0
    fig, axs = plt.subplots(2, 1, figsize=(8, 6))
    axs[0].plot(t_ms, seg, color="#4477aa", linewidth=0.8)
    axs[0].axvline(0.0, color="#cc3311", linewidth=0.8)
    if e["width_samples"] > 1:
        axs[0].axvspan(0.0, e["width_samples"] / sr * 1000.0, color="#cc3311", alpha=0.25)
    axs[0].set_title("Event %02d: %s at %.1f ms (width %d samples, amplitude %.3g)" % (
        number, e["type"], e["t_ms"], e["width_samples"], e["amplitude"]))
    axs[0].set_xlabel("ms from event start")
    if len(seg) >= 128:
        axs[1].specgram(seg, NFFT=128, Fs=sr, noverlap=112, cmap="magma")
    axs[1].set_title("Spectrogram")
    axs[1].set_ylabel("Hz")
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def write_excerpts(out_dir, x, sr, worst, n):
    import soundfile as sf
    d = os.path.join(out_dir, "excerpts")
    os.makedirs(d, exist_ok=True)
    kept = []
    for i, e in enumerate(worst[:n], 1):
        s = int(e["start_sample"])
        a, b = max(s - sr, 0), min(s + sr, len(x))
        p = os.path.join(d, "event_%02d.wav" % i)
        sf.write(p, np.clip(x[a:b], -1.0, 1.0), sr, subtype="PCM_24")
        kept.append(p)
    return kept


# ----------------------------------------------------------------------------
# Pack
# ----------------------------------------------------------------------------
def _pack_names(out_dir):
    names = ["report.md", "report.json", "events.csv", "ms.csv.gz", "report.png"]
    names += sorted(f for f in os.listdir(out_dir) if f.startswith("event_") and f.endswith(".png"))
    ex = os.path.join(out_dir, "excerpts")
    if os.path.isdir(ex):
        names += ["excerpts/" + f for f in sorted(os.listdir(ex)) if f.endswith(".wav")]
    return [n for n in names if os.path.isfile(os.path.join(out_dir, n))]


def write_zip(out_dir):
    path = os.path.join(out_dir, "analysis_pack.zip")
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in _pack_names(out_dir):
            zi = zipfile.ZipInfo(n, _ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(os.path.join(out_dir, n), "rb") as fh:
                z.writestr(zi, fh.read())
    return path, os.path.getsize(path)


# ----------------------------------------------------------------------------
# The whole run
# ----------------------------------------------------------------------------
def default_out_dir(input_path=None, compare=None):
    if compare:
        p = os.path.abspath(compare[1])
        return os.path.join(os.path.dirname(p), os.path.splitext(os.path.basename(p))[0] + "_analysis")
    p = os.path.abspath(input_path)
    if os.path.isdir(p):
        return os.path.join(p, "analysis")
    return os.path.join(os.path.dirname(p), os.path.splitext(os.path.basename(p))[0] + "_analysis")


def run(input_path=None, out_dir=None, compare=None, offset=0, max_mb=20.0, n_excerpts=10,
        block_size=None, channel=0, source=None, effects=None, monitoring=None,
        silent_input=None, make_png=True):
    """Analyse one capture and write the pack. Returns a dict: out_dir, zip, zip_bytes,
    report (the report.json content), verdict, files."""
    notes = []
    if compare:
        raw_path, proc_path = compare
        proc = load_capture(proc_path, channel)
        raw = load_capture(raw_path, channel)
        if proc["sr"] != raw["sr"]:
            raise ValueError("sample rates differ: raw %d Hz, processed %d Hz" % (raw["sr"], proc["sr"]))
        rx = raw["x"][int(offset):]
        n = min(len(rx), len(proc["x"]))
        x, rx = proc["x"][:n], rx[:n]
        cap = proc
        blocks = raw["blocks"] if (int(offset) == 0 and raw["blocks"] is not None) else None
        if raw["blocks"] is not None and blocks is None:
            notes.append("Block timing from the raw capture was not used because --offset is not 0.")
        meta = dict(raw["meta"])
        meta["source"] = "processed"
        if not block_size:
            block_size = raw["block_size"] or proc["block_size"]
        if offset:
            notes.append("The raw capture was shifted by %d samples to line it up with the processed track." % int(offset))
        notes.append("Compare mode: the verdict assumes the two files are time aligned (use --offset if not).")
        in_name, in_kind = "%s vs %s" % (os.path.basename(raw_path), os.path.basename(proc_path)), "compare"
    else:
        cap = load_capture(input_path, channel)
        x, rx, blocks = cap["x"], None, cap["blocks"]
        meta = dict(cap["meta"])
        if cap["kind"] == "folder":
            meta.setdefault("source", "raw")
        in_name, in_kind = cap["name"], cap["kind"]
    sr = cap["sr"]
    if block_size is None:
        block_size = cap["block_size"]
    if block_size is None and blocks is not None and "frames" in blocks and len(blocks["frames"]):
        block_size = int(np.median(blocks["frames"]))
    if source:
        meta["source"] = source
    if effects:
        meta["effects_off"] = effects == "off"
    if monitoring:
        meta["monitoring_off"] = monitoring == "off"
    if silent_input is not None:
        meta["silent_input"] = bool(silent_input)
    core_meta = {k: meta[k] for k in ("source", "effects_off", "monitoring_off", "silent_input",
                                              "split", "split_underflows", "split_out_blocks") if k in meta}

    if cap["channels"] > 1:
        notes.append("The input has %d channels; channel %d was analysed (the engine uses channel 0)."
                     % (cap["channels"], cap["channel"]))
    if blocks is None:
        notes.append("No blocks.csv.gz: correlation with late blocks, status flags and ADC-time gaps "
                     "was not possible, so a scheduling cause cannot be ruled in or out by timing.")
    if not block_size:
        notes.append("Block size unknown: position inside the audio block was not analysed "
                     "(give --block-size).")

    rep = cc.analyze(x, sr, block_size=block_size, blocks_table=blocks, meta=core_meta, raw=rx)
    verdict = cc.verdict(rep)
    events = build_events(rep, sr, blocks, block_size)
    worst = worst_events(events, 10)
    feats = cc.ms_features(x, sr)
    flags = ms_flags(len(feats["peak"]), feats["frame"], sr, events, blocks, block_size)

    out_dir = out_dir or default_out_dir(input_path, compare)
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):                      # a rerun must not keep old pictures
        if f.startswith("event_") and f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))
    shutil.rmtree(os.path.join(out_dir, "excerpts"), ignore_errors=True)
    for f in ("report.png",):
        if os.path.exists(os.path.join(out_dir, f)):
            os.remove(os.path.join(out_dir, f))

    png = "skipped (--no-png)"
    if make_png:
        png = make_pictures(out_dir, x, sr, events, block_size, worst)
    if png != "ok":
        notes.append("Pictures: " + png + ".")
    write_events_csv(os.path.join(out_dir, "events.csv"), events)
    if worst:
        write_excerpts(out_dir, x, sr, worst, int(n_excerpts))

    info = {"name": in_name, "kind": in_kind, "sr": int(sr), "channels": int(cap["channels"]),
            "channel": int(cap["channel"]), "n_samples": int(len(x)),
            "duration_s": len(x) / float(sr), "block_size": int(block_size) if block_size else None,
            "has_blocks": blocks is not None, "has_meta": bool(cap["meta"]),
            "ms_frame_samples": int(feats["frame"])}
    budget = float(max_mb) * 1024.0 * 1024.0
    n_ex0 = len(os.listdir(os.path.join(out_dir, "excerpts"))) if os.path.isdir(os.path.join(out_dir, "excerpts")) else 0
    attempts = [(e, n_ex0) for e in MS_DECIMATIONS] + [(MS_DECIMATIONS[-1], k) for k in range(n_ex0 - 1, -1, -1)]
    result = None
    for every, keep in attempts:
        ex_dir = os.path.join(out_dir, "excerpts")
        for i in range(keep + 1, n_ex0 + 1):
            p = os.path.join(ex_dir, "event_%02d.wav" % i)
            if os.path.exists(p):
                os.remove(p)
        rows = write_ms_csv(os.path.join(out_dir, "ms.csv.gz"), feats, flags, every)
        pnotes = list(notes)
        if every > 1:
            pnotes.append("ms.csv.gz keeps every %d%s row (peak, max_step, clip_count and flags are combined "
                          "over the group) so that the pack fits in %s MB." % (
                              every, {2: "nd", 5: "th", 10: "th"}[every], _num(max_mb)))
        if keep < n_ex0:
            pnotes.append("Only %d of %d audio excerpts kept so that the pack fits in %s MB." % (keep, n_ex0, _num(max_mb)))
        pack = {"max_mb": float(max_mb), "ms_every": int(every), "ms_rows": int(rows),
                "excerpts_kept": int(keep), "png": png if png == "ok" else "skipped", "over_limit": False}
        rj = build_report_dict(info, rep, verdict, events, pack, pnotes, meta)
        _write_reports(out_dir, rj, events)
        zp, size = write_zip(out_dir)
        result = (rj, zp, size, every, keep)
        if size <= budget:
            break
    rj, zp, size, every, keep = result
    if size > budget:
        pnotes.append("The pack is %.1f MB, above the %s MB limit, even with the smallest settings." % (
            size / 1048576.0, _num(max_mb)))
        rj["pack"]["over_limit"] = True
        rj["notes"] = _clean(pnotes)
        _write_reports(out_dir, rj, events)
        zp, size = write_zip(out_dir)
    return {"out_dir": out_dir, "zip": zp, "zip_bytes": size, "report": rj, "verdict": verdict,
            "files": _pack_names(out_dir)}


def _num(v):
    return ("%g" % float(v))


def _write_reports(out_dir, rj, events):
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(rj, fh, indent=1, allow_nan=False)
        fh.write("\n")
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(build_markdown(rj, events))


# ----------------------------------------------------------------------------
# Command line (tools/analyze_audio.py calls this)
# ----------------------------------------------------------------------------
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="analyze_audio", description="Turn a capture into an analysis pack (verdict, evidence, "
        "per-millisecond numbers, events, pictures, audio excerpts, analysis_pack.zip).")
    ap.add_argument("input", nargs="?", help="a capture folder (raw.wav, blocks.csv.gz, meta.json) or one WAV / FLAC file")
    ap.add_argument("-o", "--out", help="output folder (default: <folder>/analysis or <file>_analysis)")
    ap.add_argument("--compare", nargs=2, metavar=("RAW", "PROCESSED"),
                    help="raw sound-card capture and the processed track recorded at the same time")
    ap.add_argument("--offset", type=int, default=0, help="samples to skip at the start of RAW to line it up (compare mode)")
    ap.add_argument("--max-mb", type=float, default=20.0, help="largest analysis_pack.zip in MB (default 20)")
    ap.add_argument("--excerpts", type=int, default=10, help="audio excerpts around the worst N events (default 10)")
    ap.add_argument("--block-size", type=int, help="audio block size in samples (default: from meta.json / blocks.csv.gz)")
    ap.add_argument("--channel", type=int, default=0, help="input channel to analyse (default 0)")
    ap.add_argument("--source", choices=["raw", "processed"], help="what the file is (a capture folder is 'raw')")
    ap.add_argument("--effects", choices=["on", "off"], help="were effects on while recording?")
    ap.add_argument("--monitoring", choices=["on", "off"], help="was input monitoring on while recording?")
    ap.add_argument("--silent-input", action="store_true", default=None, help="nothing was played or sung into the input")
    ap.add_argument("--no-png", action="store_true", help="skip the pictures")
    a = ap.parse_args(argv)
    if not a.input and not a.compare:
        ap.error("give a capture folder / file, or --compare RAW PROCESSED")
    res = run(a.input, a.out, tuple(a.compare) if a.compare else None, a.offset, a.max_mb,
              a.excerpts, a.block_size, a.channel, a.source, a.effects, a.monitoring,
              a.silent_input, not a.no_png)
    print(res["verdict"]["summary"])
    print("Pack folder: %s" % res["out_dir"])
    print("Attach to a Claude chat: %s (%.2f MB)" % (res["zip"], res["zip_bytes"] / 1048576.0))
    return 0
