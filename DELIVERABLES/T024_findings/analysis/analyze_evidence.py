"""Reproduces every number in the report from the user's own matrix zips.
Usage: python analyze_evidence.py matrix_S1.zip matrix_S3.zip   (needs numpy, scipy, soundfile)
"""
import sys, os, io, json, zipfile, tempfile
import numpy as np, soundfile as sf

def extract(zp):
    d = tempfile.mkdtemp(); zipfile.ZipFile(zp).extractall(d); return d

def longest_near_zero_run(c, thr=0.01):
    """longest run of consecutive samples with |x| < thr (a 1 kHz sine of amplitude 0.12 has at most 2)."""
    best = n = 0
    for q in (np.abs(c) < thr):
        n = n + 1 if q else 0
        best = max(best, n)
    return best

def tone_stats(folder):
    x, sr = sf.read(os.path.join(folder, "raw.wav")); c = x if x.ndim == 1 else x[:, 0]
    meta = json.load(open(os.path.join(folder, "meta.json")))
    body = c[sr:]                                           # skip the first second
    t = np.arange(len(body)) / sr
    A = np.c_[np.sin(2*np.pi*1000*t), np.cos(2*np.pi*1000*t), np.ones(len(t))]
    co = np.linalg.lstsq(A, body, rcond=None)[0]; r = body - A @ co
    amp = float(np.hypot(co[0], co[1]))
    d2 = np.abs(np.diff(body, 2))
    sp = np.abs(np.fft.rfft(c[3*sr:4*sr] * np.hanning(sr))); k = int(np.argmax(sp))
    return dict(mode=meta.get("engine_mode"), channels_in=meta.get("channels_in"), seconds=round(len(c)/sr, 2),
                peak=round(float(np.abs(c).max()), 4), rms=round(float(np.sqrt((c**2).mean())), 4),
                tone_amp=round(amp, 4), resid_db=round(20*np.log10(max(np.sqrt((r**2).mean()), 1e-12)/amp*1.414), 1),
                pct_samples_2nd_diff_gt_0p03=round(float((d2 > 0.03).mean())*100, 3),
                longest_near_zero_run_first_second=longest_near_zero_run(c[:sr]),
                longest_near_zero_run_after_1s=longest_near_zero_run(body), fund_share=round(float((sp[k-3:k+4]**2).sum()/(sp**2).sum()), 3))

def s1_stats(folder):
    x, sr = sf.read(os.path.join(folder, "raw.wav")); c = x if x.ndim == 1 else x[:, 0]
    w = int(0.1*sr)
    rms100 = [round(float(np.sqrt((c[i:i+w]**2).mean()))*1000, 2) for i in range(0, 5*w, w)]
    return dict(seconds=round(len(c)/sr, 2), peak=round(float(np.abs(c).max()), 4),
                zero_fraction_first_100ms=round(float((c[:w] == 0).mean()), 3),
                rms_first_5_x100ms_e3=rms100,
                rms_after_1s_e3=round(float(np.sqrt((c[sr:]**2).mean()))*1000, 3),
                smallest_step_lsb16=1.0)

def events(folder):
    import csv
    rows = list(csv.DictReader(open(os.path.join(folder, "analysis", "events.csv"))))
    t = [float(r["t_ms"]) for r in rows if r["type"] == "click"]
    amp = [float(r["amplitude"]) for r in rows if r["type"] == "click"]
    return dict(clicks=len(t), clicks_per_s_after_1s=round(sum(1 for v in t if v > 1000)/max(1e-9, (max(t)-1000)/1000), 1) if t and max(t) > 2000 else 0,
                clicks_before_200ms=sum(1 for v in t if v < 200),
                max_click_amplitude=round(max(amp), 6) if amp else 0)

if __name__ == "__main__":
    z1, z3 = sys.argv[1], sys.argv[2]
    print("# Numbers behind the report\n")
    d1 = extract(z1); print("## S1 (silence, MME only opened)")
    for n in sorted(os.listdir(d1)):
        p = os.path.join(d1, n)
        if os.path.isdir(p): print(n, json.dumps(s1_stats(p)), json.dumps(events(p)))
    d3 = extract(z3); print("\n## S3 (tone loopback, cable green -> blue)")
    for n in sorted(os.listdir(d3)):
        p = os.path.join(d3, n)
        if os.path.isdir(p): print(n, json.dumps(tone_stats(p)), json.dumps(events(p)))
