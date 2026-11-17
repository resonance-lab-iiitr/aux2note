"""S001 replay (R-IMPORT 2026-11-14): re-derive the legacy burst numbers from raw.wav and test whether burst starts sit on a fixed time grid.
Usage: python3 legacy_replay_burst_grid.py <capture folder> [<capture folder> ...]   (needs numpy, soundfile; raw.wav stays on the owner PC)
Method = analysis/analyze_lab_captures.py of the legacy package (fit 1000 Hz sine after 1 s, residual > 0.02 = bad sample, bad samples closer than 20 samples = one burst).
Grid test: for a period P (samples) the phase concentration R = |mean(exp(2j*pi*(start mod P)/P))|; R near 1 = all starts at the same phase of P, near 1/sqrt(n) = random.
Limit: when damage is so dense that bursts merge (session 1 excl 256) or overlap, the method cannot say anything."""
import sys, json, numpy as np, soundfile as sf

def resid(c, sr, skip=1):
    body = c[sr*skip:]; t = np.arange(len(body))/sr
    A = np.c_[np.sin(2*np.pi*1000*t), np.cos(2*np.pi*1000*t), np.ones(len(t))]
    co = np.linalg.lstsq(A, body, rcond=None)[0]
    return body - A@co, float(np.hypot(co[0], co[1]))

for d in sys.argv[1:]:
    x, sr = sf.read(d + "/raw.wav"); c = x if x.ndim == 1 else x[:, 0]
    r, amp = resid(c, sr); idx = np.flatnonzero(np.abs(r) > 0.02)
    err = 20*np.log10(max(np.sqrt((r**2).mean()), 1e-12)/amp*1.414)
    if len(idx) == 0:
        print(d, json.dumps({"err_db": round(float(err), 1), "bursts": 0})); continue
    grp = np.split(idx, np.flatnonzero(np.diff(idx) > 20)+1); st = np.array([g[0] for g in grp])
    res = {"err_db": round(float(err), 1), "bursts": len(st), "n_s": round(len(r)/sr, 2)}
    if len(st) > 30:
        gap = np.diff(st)/sr*1000
        res["gap_ms"] = {"mean": round(float(gap.mean()), 1), "median": round(float(np.median(gap)), 1), "p10": round(float(np.percentile(gap, 10)), 1), "p90": round(float(np.percentile(gap, 90)), 1)}
        res["R_by_period_samples"] = {P: round(float(abs(np.exp(2j*np.pi*(st % P)/P).mean())), 3) for P in (144, 96, 192, 128, 256, 480)}
        res["share_gaps_multiple_of_3ms"] = round(float(np.mean(np.abs(gap/3-np.round(gap/3)) < 0.05)), 2)
        res["R_random_expected"] = round(1/np.sqrt(len(st)), 3)
    print(d, json.dumps(res))
