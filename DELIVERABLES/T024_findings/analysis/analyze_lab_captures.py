"""Reproduces the numbers of the 2026-11-12 Lab captures (raw.wav and output.wav).
Usage: python analyze_lab_captures.py <folder with the capture folders>   (needs numpy, soundfile)
Method: fit a 1000 Hz sine (free amplitude/phase/offset) to the samples after 1 s; residual > 0.02 = bad sample;
bad samples closer than 20 samples form one burst."""
import os, sys, json, numpy as np, soundfile as sf
sr_skip = 1
def resid(c, sr):
    body = c[sr*sr_skip:]; t = np.arange(len(body))/sr
    A = np.c_[np.sin(2*np.pi*1000*t), np.cos(2*np.pi*1000*t), np.ones(len(t))]
    co = np.linalg.lstsq(A, body, rcond=None)[0]
    return body - A@co, float(np.hypot(co[0], co[1]))
def stats(c, sr):
    r, amp = resid(c, sr); a = np.abs(r); idx = np.flatnonzero(a > 0.02)
    grp = [] if len(idx) == 0 else np.split(idx, np.flatnonzero(np.diff(idx) > 20)+1)
    err = 20*np.log10(max(np.sqrt((r**2).mean()), 1e-12)/amp*1.414)
    st = np.array([g[0] for g in grp]) if grp else np.array([])
    return dict(peak=round(float(np.abs(c).max()), 4), tone_amp=round(amp, 4), err_db=round(float(err), 1),
                bursts=len(grp), bursts_per_s=round(len(grp)/(len(r)/sr), 1), max_resid=round(float(a.max()), 3),
                median_width=float(np.median([len(g) for g in grp])) if grp else 0,
                median_gap_ms=round(float(np.median(np.diff(st))/sr*1000), 1) if len(st) > 1 else 0)
if __name__ == "__main__":
    root = sys.argv[1]
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if not os.path.exists(os.path.join(p, "meta.json")): continue
        print("==", d, json.load(open(os.path.join(p, "meta.json")))["engine_mode"])
        for fn in ("raw.wav", "output.wav"):
            x, sr = sf.read(os.path.join(p, fn)); ch = [x] if x.ndim == 1 else [x[:, i] for i in range(x.shape[1])]
            for i, c in enumerate(ch): print(" ", fn, "ch%d" % i, json.dumps(stats(c, sr)))
