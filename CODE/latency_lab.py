#!/usr/bin/env python3
"""
latency_lab.py - measure REAL audio round-trip latency on Windows (or any OS).

Why: the number shown in the looper GUI is what the driver *claims*
(PortAudio stream.latency). This tool measures what actually happens by
playing a test sweep out of the PC and recording it back through a cable.

PHYSICAL SETUP (once):
  Plug a 3.5mm male-to-male cable from the PC's GREEN (line out / speaker)
  jack into the PC's BLUE (line in) jack. Keep Windows "Listen to this
  device" OFF for the blue jack. Start with Windows output volume ~50%.

COMMANDS:
  python latency_lab.py list                      show devices per driver type
  python latency_lab.py check --api WASAPI        one quick measurement + level advice
  python latency_lab.py run                       full test matrix + report
  python latency_lab.py run --api WASAPI ASIO --blocks 64 128 256
  python latency_lab.py run --in Line --out Speakers --rates 48000 44100
  python latency_lab.py dsp-bench                 can the looper's DSP keep up?
  python latency_lab.py selftest                  verify the math (no hardware)

Put this file in the same folder as the looper's effects.py to use --dsp.
Results go to a new folder: results.csv, results.json, report.html,
recommended_settings.json
"""
import argparse
import csv
import datetime
import html
import json
import math
import os
import platform
import sys
import time

import numpy as np

from latency_core import LEAD_S, GAP_S, TAIL_S, make_chirp, build_signal, analyze  # noqa: E402  (shared with the GUI)


# ----------------------------------------------------------------------------
# Optional realistic CPU load using the looper's own effects code
# ----------------------------------------------------------------------------
def make_dsp_load(mode, chains, fs, app_dir):
    if mode == "none":
        return None
    sys.path.insert(0, app_dir)
    import effects  # the looper's effects.py
    stages = {"eq": ["eq"], "comp": ["compressor"], "reverb": ["reverb"],
              "full": ["eq", "compressor", "distortion", "delay", "reverb"]}[mode]
    objs = []
    for _ in range(chains):
        ch = effects.EffectsChain(fs)
        for name in stages:
            st = getattr(ch, name)
            if hasattr(st, "enabled"):
                st.enabled = True
        objs.append(ch)

    def run(x):
        for c in objs:
            c.process(x)
    return run


# ----------------------------------------------------------------------------
# One measurement
# ----------------------------------------------------------------------------
def run_one(sd, cfg, args, dsp_fn):
    fs, block = cfg["rate"], cfg["block"]
    sig, starts, chirp, total = build_signal(fs, args.bursts)
    in_ch, out_ch = cfg["in_ch"], cfg["out_ch"]
    rec = np.zeros((total + fs // 2, in_ch), dtype=np.float32)
    max_cb = total // block + 500
    cb_times = np.zeros(max_cb)
    st = {"pos": 0, "cb": 0, "xruns": 0}
    level = args.level

    def cb(indata, outdata, frames, time_info, status):
        t0 = time.perf_counter()
        pos = st["pos"]
        outdata.fill(0)
        n = min(frames, max(0, total - pos))
        if n > 0:
            outdata[:n, :] = (sig[pos:pos + n] * level)[:, None]
        room = max(0, min(frames, len(rec) - pos))
        if room > 0:
            rec[pos:pos + room, :] = indata[:room, :in_ch]
        if st["cb"] >= 2 and status and (status.input_overflow or status.input_underflow
                                         or status.output_underflow or status.output_overflow):
            st["xruns"] += 1
        if dsp_fn is not None:
            dsp_fn(np.ascontiguousarray(indata[:, 0]))
        st["pos"] = pos + frames
        if st["cb"] < max_cb:
            cb_times[st["cb"]] = time.perf_counter() - t0
        st["cb"] += 1

    lat = {"low": "low", "high": "high", "default": None,
           "block": block / float(fs)}[cfg["latency_mode"]]
    extra = None
    if cfg["exclusive"]:
        extra = sd.WasapiSettings(exclusive=True)
    stream = sd.Stream(device=(cfg["in_id"], cfg["out_id"]), samplerate=fs, blocksize=block,
                       channels=(in_ch, out_ch), dtype="float32", latency=lat,
                       extra_settings=extra, callback=cb)
    reported = float(stream.latency[0] + stream.latency[1]) * 1000.0
    stream.start()
    t_end = time.time() + total / fs + 6.0
    while st["pos"] < total + fs // 4 and time.time() < t_end:
        time.sleep(0.01)
    try:
        cpu = float(stream.cpu_load)
    except Exception:
        cpu = float("nan")
    stream.stop()
    stream.close()
    if st["pos"] < total:
        raise RuntimeError("stream stalled (callback stopped early)")
    # pick the input channel that actually carries the signal
    ch = int(np.argmax([np.max(np.abs(rec[:, c])) for c in range(in_ch)]))
    res = analyze(rec[:st["pos"], ch], fs, starts, chirp)
    used = cb_times[:min(st["cb"], max_cb)]
    res.update({"reported_ms": reported, "xruns": st["xruns"], "cpu_load": cpu,
                "cb_avg_ms": float(np.mean(used) * 1000), "cb_max_ms": float(np.max(used) * 1000),
                "block_ms": block / fs * 1000.0, "channel": ch})
    return res


def aggregate(cfg, runs, args):
    out = dict(cfg)
    good = [r for r in runs if "error" not in r]
    if not good:
        out.update(status="FAILED", note=runs[-1].get("error", "unknown error"))
        return out
    allv = np.array([d for r in good for d in r["delays_ms"]], dtype=float)
    det = allv[~np.isnan(allv)]
    out["expected_bursts"] = len(allv)
    out["detected"] = int(len(det))
    if len(det) == 0:
        out.update(status="NO SIGNAL", note="no sweep heard - check cable / volume / input choice",
                   reported_ms=good[0]["reported_ms"], peak_dbfs=max(r["peak_dbfs"] for r in good),
                   noise_dbfs=good[0]["noise_dbfs"])
        return out
    run_means = [float(np.nanmean(r["delays_ms"])) for r in good if not np.all(np.isnan(r["delays_ms"]))]
    run_stds = [float(np.nanstd(r["delays_ms"])) for r in good if not np.all(np.isnan(r["delays_ms"]))]
    out.update(
        measured_ms=float(np.mean(det)), median_ms=float(np.median(det)),
        min_ms=float(det.min()), max_ms=float(det.max()),
        jitter_ms=float(np.mean(run_stds)), spread_ms=float(max(run_means) - min(run_means)),
        measured_samples=float(np.mean(det) * cfg["rate"] / 1000.0),
        reported_ms=float(np.mean([r["reported_ms"] for r in good])),
        xruns=int(sum(r["xruns"] for r in good)),
        cpu_load=float(np.nanmean([r["cpu_load"] for r in good])),
        cb_avg_ms=float(np.mean([r["cb_avg_ms"] for r in good])),
        cb_max_ms=float(np.max([r["cb_max_ms"] for r in good])),
        block_ms=good[0]["block_ms"],
        peak_dbfs=float(max(r["peak_dbfs"] for r in good)),
        noise_dbfs=float(np.mean([r["noise_dbfs"] for r in good])),
        ncc_min=float(min(min(r["ncc"]) for r in good)),
    )
    out["snr_db"] = out["peak_dbfs"] - out["noise_dbfs"]
    out["gap_ms"] = out["measured_ms"] - out["reported_ms"]
    issues = []
    if out["detected"] < out["expected_bursts"]:
        issues.append("%d sweeps missed" % (out["expected_bursts"] - out["detected"]))
    if out["xruns"] > 0:
        issues.append("%d dropouts" % out["xruns"])
    if out["jitter_ms"] > 2.0:
        issues.append("jitter %.1f ms" % out["jitter_ms"])
    if out["spread_ms"] > 3.0:
        issues.append("run-to-run spread %.1f ms" % out["spread_ms"])
    if out["peak_dbfs"] > -1.0:
        issues.append("input clipping")
    if out["peak_dbfs"] < -40.0:
        issues.append("signal very quiet")
    out["status"] = "UNSTABLE" if issues else "OK"
    out["note"] = "; ".join(issues)
    m = out["measured_ms"]
    out["feel"] = ("excellent" if m < 10 else "good" if m < 20 else "playable" if m < 30
                   else "noticeable lag" if m < 50 else "poor")
    return out


# ----------------------------------------------------------------------------
# Device matrix
# ----------------------------------------------------------------------------
def pick_device(sd, api_idx, api, kind, want):
    devs = sd.query_devices()
    key = "max_%s_channels" % kind
    if want is not None:
        if str(want).isdigit():
            i = int(want)
            return i if devs[i]["hostapi"] == api_idx and devs[i][key] > 0 else None
        for i, d in enumerate(devs):
            if d["hostapi"] == api_idx and d[key] > 0 and str(want).lower() in d["name"].lower():
                return i
        return None
    i = api["default_%s_device" % kind]
    return i if i is not None and i >= 0 else None


def build_matrix(sd, args):
    devs, apis = sd.query_devices(), sd.query_hostapis()
    cfgs = []
    for ai, api in enumerate(apis):
        if args.api and not any(a.lower() in api["name"].lower() for a in args.api):
            continue
        i_id = pick_device(sd, ai, api, "input", args.indev)
        o_id = pick_device(sd, ai, api, "output", args.outdev)
        if i_id is None or o_id is None:
            print("  skip %-22s (no matching input/output device)" % api["name"])
            continue
        in_ch = min(2, devs[i_id]["max_input_channels"])
        out_ch = min(2, devs[o_id]["max_output_channels"])
        excl_opts = [False, True] if "WASAPI" in api["name"] else [False]
        for excl in excl_opts:
            for rate in args.rates:
                for block in args.blocks:
                    for lm in args.latency:
                        cfgs.append(dict(api=api["name"], in_id=i_id, out_id=o_id,
                                         in_name=devs[i_id]["name"], out_name=devs[o_id]["name"],
                                         in_ch=in_ch, out_ch=out_ch, rate=rate, block=block,
                                         latency_mode=lm, exclusive=excl))
    return cfgs


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------
FIELDS = ["status", "api", "exclusive", "rate", "block", "latency_mode", "measured_ms", "median_ms",
          "min_ms", "max_ms", "jitter_ms", "spread_ms", "reported_ms", "gap_ms", "xruns", "cpu_load",
          "cb_avg_ms", "cb_max_ms", "block_ms", "peak_dbfs", "noise_dbfs", "snr_db", "feel",
          "in_name", "out_name", "note"]


def choose_recommendations(results):
    ok = [r for r in results if r["status"] == "OK"]
    ok.sort(key=lambda r: r["measured_ms"])
    fastest = ok[0] if ok else None
    roomy = next((r for r in ok if (r["cpu_load"] != r["cpu_load"] or r["cpu_load"] <= 0.5)
                  and r["cb_max_ms"] <= 0.6 * r["block_ms"]), None)
    return fastest, roomy


def fmt(v, nd=1):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else ("%.*f" % (nd, v) if isinstance(v, float) else str(v))


def write_reports(outdir, results, meta):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "results.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    fastest, roomy = choose_recommendations(results)
    with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "results": results}, f, indent=2, default=str)
    rec = {k: v for k, v in (("fastest_stable", fastest), ("fastest_with_cpu_headroom", roomy)) if v}
    with open(os.path.join(outdir, "recommended_settings.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, default=str)

    order = {"OK": 0, "UNSTABLE": 1, "NO SIGNAL": 2, "FAILED": 3}
    rows = sorted(results, key=lambda r: (order[r["status"]], r.get("measured_ms", 1e9)))
    mx = max([r.get("measured_ms", 0) for r in rows] + [1])
    trs = []
    for r in rows:
        cls = r["status"].lower().replace(" ", "")
        bar = ""
        if "measured_ms" in r:
            bar = '<div class="bar"><span style="width:%.1f%%"></span></div>' % (100 * r["measured_ms"] / mx)
        cells = [r["status"], r["api"] + (" (exclusive)" if r["exclusive"] else ""), r["rate"], r["block"],
                 r["latency_mode"], fmt(r.get("measured_ms")) + bar, fmt(r.get("jitter_ms"), 2),
                 fmt(r.get("reported_ms")), fmt(r.get("gap_ms")), fmt(r.get("xruns", None)),
                 fmt(r.get("cpu_load", None) * 100 if r.get("cpu_load") == r.get("cpu_load") and "cpu_load" in r else None, 0),
                 r.get("feel", ""), r.get("note", "")]
        trs.append('<tr class="%s">%s</tr>' % (cls, "".join("<td>%s</td>" % (c if i == 5 else html.escape(str(c)))
                                                           for i, c in enumerate(cells))))

    def card(title, r):
        if not r:
            return '<div class="card"><h3>%s</h3><p>none found</p></div>' % title
        return ('<div class="card"><h3>%s</h3><p class="big">%.1f ms</p><p>%s%s, %d Hz, block %d, latency=%s</p>'
                '<p>jitter %.2f ms, dropouts %d</p></div>') % (
            title, r["measured_ms"], html.escape(r["api"]), " exclusive" if r["exclusive"] else "",
            r["rate"], r["block"], r["latency_mode"], r["jitter_ms"], r["xruns"])
    doc = """<!doctype html><html><head><meta charset="utf-8"><title>Latency report</title>
<style>:root{--bg:#fff;--fg:#1d1d1f;--mut:#666;--line:#ddd;--ok:#1a7f37;--bad:#b42318;--warn:#b54708;--bar:#3b82f6}
@media(prefers-color-scheme:dark){:root{--bg:#161618;--fg:#eee;--mut:#999;--line:#333;--ok:#4ade80;--bad:#f87171;--warn:#fbbf24;--bar:#60a5fa}}
body{background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif;margin:24px}table{border-collapse:collapse;width:100%%}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--mut)}
.cards{display:flex;gap:16px;flex-wrap:wrap}.card{border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:260px}
.big{font-size:28px;margin:4px 0}.ok td:first-child{color:var(--ok)}.unstable td:first-child{color:var(--warn)}
.failed td:first-child,.nosignal td:first-child{color:var(--bad)}.bar{background:var(--line);height:5px;margin-top:3px;min-width:80px}
.bar span{display:block;height:5px;background:var(--bar)}.scroll{overflow-x:auto}small{color:var(--mut)}</style></head><body>
<h1>Round-trip latency report</h1><p><small>%s | %s | Python %s | sounddevice %s | %s</small></p>
<div class="cards">%s%s</div>
<h2>All configurations</h2><div class="scroll"><table><tr><th>Status</th><th>Driver</th><th>Rate</th><th>Block</th><th>Latency mode</th>
<th>Measured RTT (ms)</th><th>Jitter (ms)</th><th>GUI-style reported (ms)</th><th>Measured minus reported</th><th>Dropouts</th>
<th>CPU %%</th><th>Feel</th><th>Notes</th></tr>%s</table></div>
<h2>How to read this</h2><ul>
<li><b>Measured RTT</b> is the true delay from the app writing audio to hearing it come back in (equals live monitoring latency in a pass-through looper).</li>
<li><b>Reported</b> is what the driver claims; the GUI shows this kind of number. A positive "measured minus reported" means the GUI under-reports.</li>
<li><b>Jitter</b> is how much the delay wobbles between sweeps; keep it under about 1 ms. <b>Dropouts</b> must be 0.</li>
<li>Rule of thumb: under 10 ms feels instant, 10-20 ms good, 20-30 ms playable, over 50 ms hard to play.</li></ul>
</body></html>""" % (html.escape(meta["when"]), html.escape(meta["os"]), meta["python"], meta["sounddevice"],
                    html.escape(meta["portaudio"]), card("Fastest stable", fastest),
                    card("Fastest with CPU headroom", roomy), "".join(trs))
    with open(os.path.join(outdir, "report.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return fastest, roomy


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def import_sd():
    try:
        import sounddevice as sd
        return sd
    except Exception as e:
        sys.exit("Cannot load sounddevice/PortAudio: %s\n  pip install sounddevice" % e)


def cmd_list(args):
    sd = import_sd()
    devs = sd.query_devices()
    for ai, api in enumerate(sd.query_hostapis()):
        print("\n== %s ==" % api["name"])
        for i, d in enumerate(devs):
            if d["hostapi"] != ai:
                continue
            print("  [%2d] %-45s in:%d out:%d  %5.0f Hz  driver-claimed low latency in/out: %.1f/%.1f ms" % (
                i, d["name"][:45], d["max_input_channels"], d["max_output_channels"], d["default_samplerate"],
                d["default_low_input_latency"] * 1000, d["default_low_output_latency"] * 1000))


def cmd_run(args):
    sd = import_sd()
    cfgs = build_matrix(sd, args)
    if args.cmd == "check":
        cfgs, args.repeats, args.bursts = cfgs[:1], 1, 4
    if not cfgs:
        sys.exit("No usable configurations. Run 'list' and pass --in/--out/--api.")
    print("Testing %d configurations x %d repeats (about %.0f s)...\n" % (
        len(cfgs), args.repeats, len(cfgs) * args.repeats * (LEAD_S + args.bursts * GAP_S + TAIL_S + 0.5)))
    results = []
    for n, cfg in enumerate(cfgs, 1):
        dsp = make_dsp_load(args.dsp, args.dsp_chains, cfg["rate"], args.app_dir)
        runs = []
        for _ in range(args.repeats):
            try:
                runs.append(run_one(sd, cfg, args, dsp))
            except Exception as e:
                runs.append({"error": str(e).replace("\n", " ")[:200]})
                break
        r = aggregate(cfg, runs, args)
        results.append(r)
        print("[%2d/%d] %-18s %5d Hz blk %-4d %-7s%s -> %-9s %s" % (
            n, len(cfgs), r["api"][:18], r["rate"], r["block"], r["latency_mode"],
            " excl" if r["exclusive"] else "     ", r["status"],
            ("RTT %.1f ms (GUI would say %.1f) jitter %.2f xruns %d" % (
                r["measured_ms"], r["reported_ms"], r["jitter_ms"], r["xruns"])) if "measured_ms" in r else r.get("note", "")))
        if args.cmd == "check" and "peak_dbfs" in r:
            p = r["peak_dbfs"]
            print("\nCaptured sweep level: %.1f dBFS (noise floor %.1f dBFS)" % (p, r["noise_dbfs"]))
            print("  aim for -20 .. -6 dBFS. " + (
                "Too quiet: raise Windows output volume / line-in level." if p < -30 else
                "Too loud: lower Windows output volume." if p > -3 else "Level is good."))
    meta = {"when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "os": "%s %s" % (platform.system(), platform.version()), "python": platform.python_version(),
            "sounddevice": sd.__version__, "portaudio": sd.get_portaudio_version()[1],
            "dsp": args.dsp, "dsp_chains": args.dsp_chains, "level": args.level}
    outdir = args.outdir or "latency_results_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fastest, roomy = write_reports(outdir, results, meta)
    print("\nReports written to: %s  (open report.html)" % os.path.abspath(outdir))
    if fastest:
        print("FASTEST STABLE: %s%s %d Hz block %d latency=%s -> %.1f ms" % (
            fastest["api"], " exclusive" if fastest["exclusive"] else "", fastest["rate"], fastest["block"],
            fastest["latency_mode"], fastest["measured_ms"]))
    else:
        print("No fully stable configuration found - see report.html for the reasons.")


def cmd_dsp_bench(args):
    sys.path.insert(0, args.app_dir)
    try:
        import effects
    except Exception as e:
        sys.exit("Cannot import effects.py from %s: %s" % (args.app_dir, e))
    fs = 48000
    print("Time to process ONE mono block per effect, as % of the time available (block length).")
    print("Over ~50% = will crackle once several tracks run. Over 100% = guaranteed dropouts.\n")
    stages = ["eq", "compressor", "distortion", "delay", "reverb"]
    print("%-12s" % "effect" + "".join("%12s" % ("blk %d" % b) for b in args.blocks))
    for name in stages + ["ALL"]:
        ch = effects.EffectsChain(fs)
        for s in stages:
            st = getattr(ch, s)
            if hasattr(st, "enabled"):
                st.enabled = (name == "ALL") or (s == name)
        row = "%-12s" % name
        for b in args.blocks:
            x = (np.random.randn(b) * 0.1).astype(np.float32)
            for _ in range(5):
                ch.process(x)
            t = []
            for _ in range(60):
                t0 = time.perf_counter(); ch.process(x); t.append(time.perf_counter() - t0)
            pct = 100.0 * np.mean(t) / (b / fs)
            row += "%11.0f%%" % pct
        print(row)
    print("\n(one chain = one track or the master bus; the looper runs one per track plus master)")


def cmd_selftest(args):
    print("Self-test: synthetic loopback with known delays")
    rng = np.random.default_rng(1)
    ok = True
    for fs in (44100, 48000):
        sig, starts, chirp, total = build_signal(fs, 6)
        for true_ms in (3.3, 17.77, 49.0, 212.4):
            d = true_ms / 1000 * fs
            n = len(sig) + 2 * fs
            f = np.fft.rfftfreq(n, 1.0 / fs)
            pad = np.concatenate([sig, np.zeros(n - len(sig))])
            rec = np.fft.irfft(np.fft.rfft(pad) * np.exp(-2j * np.pi * f * d / fs), n)[:total + fs // 2]
            rec = 0.4 * rec + rng.normal(0, 0.003, len(rec))
            r = analyze(rec, fs, starts, chirp)
            got = np.nanmean(r["delays_ms"])
            good = abs(got - true_ms) < 0.05 and not np.isnan(r["delays_ms"]).any()
            ok &= good
            print("  fs %5d  true %7.2f ms  measured %7.3f ms  %s" % (fs, true_ms, got, "PASS" if good else "FAIL"))
    r = analyze(rng.normal(0, 0.003, int(6 * 48000)), 48000, build_signal(48000, 6)[1], make_chirp(48000))
    miss = bool(np.isnan(r["delays_ms"]).all())
    ok &= miss
    print("  noise only -> all sweeps reported missed: %s" % ("PASS" if miss else "FAIL"))
    print("SELFTEST " + ("PASSED" if ok else "FAILED"))
    sys.exit(0 if ok else 1)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["list", "check", "run", "dsp-bench", "selftest"])
    p.add_argument("--api", nargs="*", help="driver types to test, e.g. WASAPI ASIO WDM-KS MME DirectSound")
    p.add_argument("--in", dest="indev", help="input device id or name part (e.g. Line)")
    p.add_argument("--out", dest="outdev", help="output device id or name part (e.g. Speakers)")
    p.add_argument("--rates", nargs="*", type=int, default=[48000])
    p.add_argument("--blocks", nargs="*", type=int, default=[32, 64, 128, 256, 512])
    p.add_argument("--latency", nargs="*", default=["low"], choices=["low", "high", "default", "block"],
                   help="'default' reproduces the looper app's current setting")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--bursts", type=int, default=6)
    p.add_argument("--level", type=float, default=0.35, help="test sweep amplitude 0..1")
    p.add_argument("--dsp", choices=["none", "eq", "comp", "reverb", "full"], default="none",
                   help="add the looper's real effect processing as CPU load")
    p.add_argument("--dsp-chains", type=int, default=1, help="number of effect chains (tracks) to simulate")
    p.add_argument("--app-dir", default=here)
    p.add_argument("--outdir")
    args = p.parse_args()
    {"list": cmd_list, "check": cmd_run, "run": cmd_run, "dsp-bench": cmd_dsp_bench,
     "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    main()
