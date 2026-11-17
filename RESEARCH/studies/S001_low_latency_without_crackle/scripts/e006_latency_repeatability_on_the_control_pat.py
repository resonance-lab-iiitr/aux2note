#!/usr/bin/env python3
"""E006 : latency repeatability on the control paths (study S001, stage 0 calibration).

Runs on the OWNER'S PC from the project folder (the folder that holds CODE/ and RESEARCH/):

    python RESEARCH/studies/S001_low_latency_without_crackle/scripts/e006_latency_repeatability_on_the_control_pat.py

What it does (the card in experiments/E006_*.md is the authority; this file only runs it):
  0. checks the sound devices and does ONE throw-away shared run to see the signal level (not recorded as data)
  1. WASAPI shared 48000 Hz, block 256, latency "low": 5 runs, one fresh process per run
  2. MME same settings: 5 runs
  3. asks you to PULL THE CABLE out of the Line In jack, 1 run per path (must hear nothing), then asks you to plug it back
  4. writes results/E006_<label>.zip with runs.csv, settings.json, preview.txt, notes.txt and the manifest

The measurement itself is CODE/latency_lab.py run_one / aggregate (read-only import, same code as the app's calibration
arithmetic in CODE/latency_core.py). Nothing in CODE/ is changed.

    --selftest   no hardware: runs the whole procedure against a simulated loopback and builds a pack that rpack.py check accepts
    --yes        do not wait for Enter at the prompts (for selftest / unattended runs; the cable steps then CANNOT be done)
    --no-devices leave device names out of the environment record
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]                      # PROJECT/
sys.path.insert(0, str(ROOT / "CODE"))
sys.path.insert(0, str(ROOT / "RESEARCH" / "lib"))

import numpy as np  # noqa: E402

EXP = "E006"
SCRIPT_VERSION = "1"
RATE, BLOCK, LATENCY = 48000, 256, "low"
BURSTS, LEVEL = 6, 0.35
RUNS = 5
PATHS = [("shared", "WASAPI", False), ("mme", "MME", False)]   # name, host API substring, exclusive
PEAK_LO, PEAK_HI = -30.0, -3.0              # advice range (card pass rule: captured peak between -30 and -3 dBFS)

NOTE_QUESTIONS = [
    ("windows_volume_percent", "Windows output volume of Speakers in % (the slider value)"),
    ("realtek_driver", "Realtek driver name and VERSION (Device Manager > Sound controllers > Realtek > Driver tab)"),
    ("device_formats", "Default format of Line In and of Speakers (Sound control panel > Advanced), e.g. 24 bit 48000 Hz"),
    ("exclusive_options", "Exclusive mode options on both devices (allow / give priority: ticked or not)"),
    ("enhancements", "Enhancements / audio effects: on or off"),
    ("listen_to_device", "'Listen to this device' on Line In: off? (must be off)"),
    ("power_plan", "Windows power plan"),
    ("other_programs", "Audio programs that were open (should be none)"),
    ("heard_or_printed", "Anything you heard, or any error text word for word"),
]


# ----------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def die(msg):
    print("\nSTOP: " + msg, file=sys.stderr)
    raise SystemExit(2)


def import_latency_lab():
    try:
        import latency_lab
        return latency_lab
    except Exception as e:                  # plain message, no traceback wall
        die("cannot import CODE/latency_lab.py (%s). Run this script from the project folder that contains CODE/." % e)


class FakeSD:
    """Simulated sounddevice for --selftest / --fake: a loopback with a known delay per host API.
    Not a model of any real driver. Runs the callbacks synchronously inside start()."""
    __version__ = "fake-0"
    DELAY_MS = {"Windows WASAPI": 41.30, "MME": 62.80}

    def __init__(self, cable=True, missing_line=False, run_index=0):
        self.cable, self.missing_line, self.run_index = cable, missing_line, run_index
        self._hostapis = [{"name": "MME", "default_input_device": 0, "default_output_device": 1},
                          {"name": "Windows WASAPI", "default_input_device": 2, "default_output_device": 3}]
        self._devs = [
            {"name": "Microphone (Webcam)", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speakers (Realtek High Def", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
            {"name": "Microphone (Webcam)", "hostapi": 1, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000.0},
            {"name": "Speakers (Realtek High Definition Audio)", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
        ]
        if not missing_line:
            self._devs += [
                {"name": "Line In (Realtek High Def", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
                {"name": "Line In (Realtek High Definition Audio)", "hostapi": 1, "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000.0},
            ]

    def query_devices(self):
        return self._devs

    def query_hostapis(self):
        return self._hostapis

    def get_portaudio_version(self):
        return (1900, "PortAudio fake")

    def WasapiSettings(self, exclusive=False):
        return ("wasapi", exclusive)

    def Stream(self, device, samplerate, blocksize, channels, dtype, latency, extra_settings, callback):
        return _FakeStream(self, device, samplerate, blocksize, channels, callback)


class _FakeStream:
    def __init__(self, sd, device, fs, block, channels, cb):
        self.sd, self.fs, self.block, self.cb = sd, fs, block, cb
        self.in_ch, self.out_ch = channels
        api = sd._devs[device[0]]["hostapi"]
        self.api_name = sd._hostapis[api]["name"]
        self.latency = (block / fs, block / fs)
        self.cpu_load = 0.05

    def start(self):
        rng = np.random.default_rng(1000 + self.sd.run_index)
        delay = int(round((self.sd.DELAY_MS[self.api_name] + 0.13 * (self.sd.run_index % 3)) / 1000 * self.fs))
        status = types.SimpleNamespace(input_overflow=False, input_underflow=False,
                                       output_underflow=False, output_overflow=False)
        ring = np.zeros(delay + 4 * self.block, dtype=np.float64)
        total_blocks = int((self.fs * 8.0) // self.block)
        wpos = 0
        for _ in range(total_blocks):
            outdata = np.zeros((self.block, self.out_ch), dtype=np.float32)
            indata = np.zeros((self.block, self.in_ch), dtype=np.float32)
            # input of this block = output delayed by `delay` samples
            src = np.arange(wpos - delay, wpos - delay + self.block)
            for k, s in enumerate(src):
                indata[k, 0] = ring[s % len(ring)] if s >= 0 and self.sd.cable else 0.0
            indata += (rng.normal(0, 0.002, indata.shape)).astype(np.float32)
            self.cb(indata, outdata, self.block, None, status)
            for k in range(self.block):
                ring[(wpos + k) % len(ring)] = 0.45 * outdata[k, 0]
            wpos += self.block

    def stop(self):
        pass

    def close(self):
        pass


def get_sd(fake, phase="plugged", run_index=0, missing_line=False):
    if fake:
        return FakeSD(cable=(phase != "unplugged"), missing_line=missing_line, run_index=run_index)
    try:
        import sounddevice as sd
        return sd
    except Exception as e:
        die("cannot load sounddevice / PortAudio (%s). Install the app requirements first: pip install sounddevice" % e)


def find_cfg(sd, ll, api_sub, excl, want_in, want_out):
    """Build the config dict latency_lab.run_one expects, or die with a plain message listing what exists."""
    devs, apis = sd.query_devices(), sd.query_hostapis()
    ai = next((i for i, a in enumerate(apis) if api_sub.lower() in a["name"].lower()), None)
    if ai is None:
        die("host API containing '%s' not found. Available: %s" % (api_sub, ", ".join(a["name"] for a in apis)))
    api = apis[ai]
    i_id = ll.pick_device(sd, ai, api, "input", want_in)
    o_id = ll.pick_device(sd, ai, api, "output", want_out)
    if i_id is None or o_id is None:
        names = ["[%d] %s (in %d / out %d)" % (i, d["name"], d["max_input_channels"], d["max_output_channels"])
                 for i, d in enumerate(devs) if d["hostapi"] == ai]
        die("under %s no input matching '%s' or no output matching '%s'. Devices there:\n  %s\n"
            "Use --in / --out with a part of the right name, and do NOT use the webcam microphone."
            % (api["name"], want_in, want_out, "\n  ".join(names)))
    return dict(api=api["name"], in_id=i_id, out_id=o_id, in_name=devs[i_id]["name"], out_name=devs[o_id]["name"],
                in_ch=min(2, devs[i_id]["max_input_channels"]), out_ch=min(2, devs[o_id]["max_output_channels"]),
                rate=RATE, block=BLOCK, latency_mode=LATENCY, exclusive=excl)


def one_measurement(sd, ll, cfg):
    args = types.SimpleNamespace(bursts=BURSTS, level=LEVEL, dsp="none", dsp_chains=1)
    try:
        res = ll.run_one(sd, cfg, args, None)
        out = ll.aggregate(cfg, [res], args)
    except Exception as e:
        out = dict(cfg)
        out.update(status="FAILED", note=str(e).replace("\n", " ")[:300])
    out["_error"] = out.get("note", "") if out.get("status") == "FAILED" else ""
    return out


def row_from(out, path, phase, idx):
    g = lambda k: out.get(k, "")
    r = dict(run_id="%s_%s_%d" % (path, phase, idx), path=path, phase=phase, run_index=idx,
             timestamp=datetime.datetime.now().isoformat(timespec="seconds"), status=g("status"),
             expected_bursts=g("expected_bursts") if g("expected_bursts") != "" else BURSTS,
             detected=g("detected") if g("detected") != "" else 0,
             median_ms=g("median_ms"), min_ms=g("min_ms"), max_ms=g("max_ms"),
             jitter_range_ms=(out["max_ms"] - out["min_ms"]) if "max_ms" in out and "min_ms" in out else "",
             jitter_std_ms=g("jitter_ms"), xruns=g("xruns"), peak_dbfs=g("peak_dbfs"), noise_dbfs=g("noise_dbfs"),
             reported_ms=g("reported_ms"), gap_ms=g("gap_ms"), cb_avg_ms=g("cb_avg_ms"), cb_max_ms=g("cb_max_ms"),
             cpu_load=g("cpu_load"), in_name=g("in_name"), out_name=g("out_name"), error=out.get("_error", ""))
    for k, v in r.items():
        if isinstance(v, float):
            r[k] = round(v, 4)
    return r


# ----------------------------------------------------------------------------------------------
# child mode: ONE measurement in a fresh process, result to a json file
# ----------------------------------------------------------------------------------------------
def child_main(a):
    ll = import_latency_lab()
    path = next(p for p in PATHS if p[0] == a.path)
    sd = get_sd(a.fake, a.phase, a.run_index)
    cfg = find_cfg(sd, ll, path[1], path[2], a.indev, a.outdev)
    out = one_measurement(sd, ll, cfg)
    Path(a.json).write_text(json.dumps(out, default=str), encoding="utf-8")
    return 0


def run_in_fresh_process(a, path, phase, idx, tmpdir):
    jpath = Path(tmpdir) / ("%s_%s_%d.json" % (path, phase, idx))
    cmd = [sys.executable, str(HERE), "--child", "--path", path, "--phase", phase, "--run-index", str(idx),
           "--json", str(jpath), "--in", a.indev, "--out", a.outdev]
    if a.fake:
        cmd.append("--fake")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if not jpath.exists():
        return dict(status="FAILED", note=("child failed: " + (p.stderr or p.stdout)[-300:]).replace("\n", " "),
                    _error="child process produced no result", api=path)
    return json.loads(jpath.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------------------
# summary maths (also used by the selftest on known numbers)
# ----------------------------------------------------------------------------------------------
def spread(values):
    v = [float(x) for x in values if x not in ("", None)]
    return (max(v) - min(v)) if v else float("nan")


def summarize_rows(rows):
    """Per path numbers for the pack metrics. Plugged runs only, except the unplugged detections."""
    m = {}
    for name, _, _ in PATHS:
        pl = [r for r in rows if r["path"] == name and r["phase"] == "plugged"]
        un = [r for r in rows if r["path"] == name and r["phase"] == "unplugged"]
        meds = [r["median_ms"] for r in pl if r["median_ms"] != ""]
        m[name + "_runs"] = len(pl)
        m[name + "_runs_all_bursts"] = sum(1 for r in pl if r["detected"] == BURSTS)
        m[name + "_runs_status_ok"] = sum(1 for r in pl if r["status"] == "OK")
        m[name + "_median_of_run_medians_ms"] = round(statistics.median(meds), 3) if meds else None
        m[name + "_run_median_min_ms"] = round(min(meds), 3) if meds else None
        m[name + "_run_median_max_ms"] = round(max(meds), 3) if meds else None
        m[name + "_run_median_spread_ms"] = round(spread(meds), 3) if meds else None
        m[name + "_max_within_run_range_ms"] = round(max([r["jitter_range_ms"] for r in pl if r["jitter_range_ms"] != ""] or [float("nan")]), 3)
        m[name + "_xruns_total"] = sum(int(r["xruns"] or 0) for r in pl)
        pk = [r["peak_dbfs"] for r in pl if r["peak_dbfs"] != ""]
        m[name + "_peak_dbfs_min"] = round(min(pk), 2) if pk else None
        m[name + "_peak_dbfs_max"] = round(max(pk), 2) if pk else None
        m[name + "_unplugged_detected"] = (un[0]["detected"] if un else None)
        m[name + "_unplugged_status"] = (un[0]["status"] if un else None)
    m["n_runs_per_path_requested"] = RUNS
    return {k: (v if v == v else None) if not isinstance(v, float) else (None if v != v else v) for k, v in m.items()}


def preview_text(m):
    """A convenience read of the numbers against the card rule. NOT the verdict: R-ANALYZE decides."""
    L = ["PREVIEW ONLY (the official verdict is made by the analysis session from the card's rule).", ""]
    ok_all = True
    spreads = []
    for name, _, _ in PATHS:
        wr = m[name + "_max_within_run_range_ms"]
        runs_ok = (m[name + "_runs_all_bursts"] == RUNS and m[name + "_runs_status_ok"] == RUNS and m[name + "_xruns_total"] == 0
                   and wr is not None and wr <= 3.0)
        pk_ok = m[name + "_peak_dbfs_min"] is not None and m[name + "_peak_dbfs_min"] >= PEAK_LO and m[name + "_peak_dbfs_max"] <= PEAK_HI
        sp = m[name + "_run_median_spread_ms"]
        un_ok = m[name + "_unplugged_detected"] == 0
        L.append("%-7s runs with 6/6 bursts, status OK, 0 xruns, within-run range <= 3.0 ms: %s | peak in %d..%d dBFS: %s | spread of run medians: %s ms | unplugged heard nothing: %s"
                 % (name, "yes" if runs_ok else "NO", PEAK_LO, PEAK_HI, "yes" if pk_ok else "NO", sp, "yes" if un_ok else "NO"))
        L.append("        median of run medians %s ms (min %s, max %s), worst within-run range %s ms"
                 % (m[name + "_median_of_run_medians_ms"], m[name + "_run_median_min_ms"],
                    m[name + "_run_median_max_ms"], m[name + "_max_within_run_range_ms"]))
        ok_all &= bool(runs_ok and pk_ok and un_ok)
        spreads.append(sp if sp is not None else 1e9)
    spread_ok = min(spreads) <= 1.0 and max(spreads) <= 3.0
    L += ["", "spread rule (1.0 ms or less on at least one path, 3.0 ms or less on both): %s" % ("yes" if spread_ok else "NO"),
          "all other conditions met: %s" % ("yes" if ok_all else "NO")]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------
# main procedure
# ----------------------------------------------------------------------------------------------
def wait_enter(a, text):
    print("\n>>> " + text)
    if a.yes:
        return
    if not sys.stdin or not sys.stdin.isatty():
        die("this step needs a person at the keyboard (press Enter). Run it in a normal terminal, not piped.")
    input("    press Enter when done... ")


def collect_notes(a, auto):
    if a.notes:
        return Path(a.notes).read_text(encoding="utf-8")
    lines = ["Notes for E006 (%s). Automatic facts first, then your answers." % datetime.date.today().isoformat()]
    lines += ["auto: %s = %s" % (k, v) for k, v in auto.items()]
    for key, q in NOTE_QUESTIONS:
        if a.yes or not sys.stdin or not sys.stdin.isatty():
            ans = a.note_default
        else:
            ans = input("  %s: " % q).strip() or "unknown"
        lines.append("%s: %s" % (key, ans))
    return "\n".join(lines) + "\n"


def main_run(a):
    import rpack
    ll = import_latency_lab()
    sd = get_sd(a.fake)
    # ---- preflight: devices named explicitly, never the default input (webcam microphone risk, F-14)
    cfgs = {name: find_cfg(sd, ll, sub, excl, a.indev, a.outdev) for name, sub, excl in PATHS}
    print("E006 devices:")
    for name, c in cfgs.items():
        print("  %-7s %-16s in [%d] %s | out [%d] %s | %d Hz block %d latency %s%s"
              % (name, c["api"], c["in_id"], c["in_name"], c["out_id"], c["out_name"], RATE, BLOCK, LATENCY,
                 " exclusive" if c["exclusive"] else ""))
    low = [c["in_name"] for c in cfgs.values() if "line" not in c["in_name"].lower()]
    if low:
        die("the chosen input is not a Line In: %s. Use --in with the right name part." % ", ".join(low))
    label = a.label or datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path(a.out_dir)
    files_dir = out_dir / ("E006_%s_files" % label)
    files_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="e006_")

    # ---- throw-away level check (shared, not recorded as data)
    wait_enter(a, "Cable plugged: green jack (Speakers) to blue jack (Line In). Windows volume about 50 %. Other audio programs closed. "
                  "'Listen to this device' off.")
    print("Level check (throw-away run, about 8 s)...")
    pre = run_in_fresh_process(a, "shared", "plugged", 0, tmp)
    if pre.get("status") in ("FAILED", "NO SIGNAL") or "peak_dbfs" not in pre:
        die("level check: %s %s. Check cable, jacks, 'Listen to this device' off, Line In as the chosen input, then run again."
            % (pre.get("status"), pre.get("note", "")))
    pk = pre["peak_dbfs"]
    print("  captured peak %.1f dBFS (aim for %d .. %d)" % (pk, PEAK_LO, PEAK_HI))
    if not (PEAK_LO <= pk <= PEAK_HI):
        die("level out of range (%.1f dBFS). %s Then run this script again; keep the volume the same for the whole experiment."
            % (pk, "Raise the Windows Speakers volume." if pk < PEAK_LO else "Lower the Windows Speakers volume."))

    # ---- the experiment
    rows = []
    for name, _, _ in PATHS:
        for i in range(1, RUNS + 1):
            out = run_in_fresh_process(a, name, "plugged", i, tmp)
            r = row_from(out, name, "plugged", i)
            rows.append(r)
            print("  %-7s run %d: %-9s detected %s/6 median %s ms range %s ms xruns %s peak %s dBFS %s"
                  % (name, i, r["status"], r["detected"], r["median_ms"], r["jitter_range_ms"], r["xruns"], r["peak_dbfs"], r["error"]))
    wait_enter(a, "NOW PULL THE CABLE out of the blue Line In jack (leave the other end). Nothing else changes.")
    for name, _, _ in PATHS:
        out = run_in_fresh_process(a, name, "unplugged", 1, tmp)
        r = row_from(out, name, "unplugged", 1)
        rows.append(r)
        print("  %-7s UNPLUGGED: %s detected %s/6 %s" % (name, r["status"], r["detected"], r["error"]))
    wait_enter(a, "PLUG THE CABLE BACK (if you will do more tests). Then fill in the notes questions.")

    # ---- files and pack
    cols = list(rows[0].keys())
    with open(files_dir / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    settings = dict(experiment=EXP, script_version=SCRIPT_VERSION, label=label, started=datetime.datetime.now().isoformat(timespec="seconds"),
                    rate=RATE, block=BLOCK, latency=LATENCY, bursts=BURSTS, level=LEVEL, runs_per_path=RUNS,
                    paths=[dict(name=n, **{k: v for k, v in cfgs[n].items()}) for n, _, _ in PATHS],
                    one_process_per_run=True, level_check_peak_dbfs=pk, selftest_or_fake=bool(a.fake),
                    script_sha256=sha256_file(HERE), latency_lab_sha256=sha256_file(ROOT / "CODE" / "latency_lab.py"),
                    latency_core_sha256=sha256_file(ROOT / "CODE" / "latency_core.py"))
    (files_dir / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    m = summarize_rows(rows)
    (files_dir / "preview.txt").write_text(preview_text(m), encoding="utf-8")
    print("\n" + preview_text(m))
    auto = {"latency_lab_sha256": settings["latency_lab_sha256"][:12], "script_version": SCRIPT_VERSION,
            "level_check_peak_dbfs": round(pk, 1)}
    notes = collect_notes(a, auto)
    p = rpack.ResultPack(EXP, label, str(out_dir), devices=not a.no_devices)
    for fn in ("runs.csv", "settings.json", "preview.txt"):
        p.add_file(files_dir / fn)
    p.metrics(**{k: v for k, v in m.items() if v is not None})
    p.notes(notes)
    zpath = p.finish()
    print("\nSend back: %s  (attach it with the latest PROJECT zip)" % zpath)
    return zpath


# ----------------------------------------------------------------------------------------------
# selftest (no hardware)
# ----------------------------------------------------------------------------------------------
def selftest():
    import rpack
    ok = True

    def check(cond, text):
        nonlocal ok
        ok &= bool(cond)
        print("  %-4s %s" % ("PASS" if cond else "FAIL", text))

    print("E006 selftest (simulated loopback, no hardware)")
    check(abs(spread([19.2, 19.9, 19.4]) - 0.7) < 1e-9, "spread() of known numbers")
    with tempfile.TemporaryDirectory() as td:
        a = argparse.Namespace(indev="Line", outdev="Speakers", label="selftest", out_dir=td, yes=True, fake=True,
                               no_devices=True, notes=None, note_default="selftest answer")
        zpath = main_run(a)
        m, probs = rpack.check(str(zpath))
        check(not probs, "rpack.check accepts the pack (%s)" % (probs or "no problems"))
        mm = m["metrics"]
        check(mm["shared_runs_all_bursts"] == RUNS and mm["mme_runs_all_bursts"] == RUNS, "all 6 bursts detected in 5 of 5 runs on both paths")
        check(abs(mm["shared_median_of_run_medians_ms"] - 41.43) < 0.15, "shared median %s ms close to the simulated 41.3-41.56 ms" % mm["shared_median_of_run_medians_ms"])
        check(abs(mm["mme_median_of_run_medians_ms"] - 62.93) < 0.15, "MME median %s ms close to the simulated 62.8-63.06 ms" % mm["mme_median_of_run_medians_ms"])
        check(mm["shared_run_median_spread_ms"] <= 0.5 and mm["mme_run_median_spread_ms"] <= 0.5, "run median spread matches the simulated 0.26 ms jitter")
        check(mm["shared_unplugged_detected"] == 0 and mm["mme_unplugged_detected"] == 0, "unplugged (no cable) runs detect 0 bursts")
        check(mm["shared_xruns_total"] == 0, "no xruns in the simulation")
        names = [e["name"] for e in m["files"]]
        check(set(names) == {"runs.csv", "settings.json", "preview.txt"}, "pack files %s" % names)
        rows = list(csv.DictReader(open(Path(td) / "E006_selftest_files" / "runs.csv", encoding="utf-8")))
        check(len(rows) == 2 * RUNS + 2, "runs.csv has %d rows (5 + 5 plugged, 2 unplugged)" % len(rows))
        check(all(r["error"] == "" for r in rows), "no run errors")
    # early failure with a plain message when the Line In device is missing
    ll = import_latency_lab()
    try:
        find_cfg(FakeSD(missing_line=True), ll, "WASAPI", False, "Line", "Speakers")
        check(False, "missing Line In stops early")
    except SystemExit as e:
        check(e.code == 2, "missing Line In stops early with a plain message")
    print("SELFTEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def parse():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="indev", default="Line", help="input device name part (default Line)")
    ap.add_argument("--out", dest="outdev", default="Speakers", help="output device name part (default Speakers)")
    ap.add_argument("--label", help="run label for the pack (default: date and time)")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--notes", help="path of a filled notes text file instead of the questions")
    ap.add_argument("--yes", action="store_true", help="do not wait for Enter (selftest only)")
    ap.add_argument("--no-devices", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fake", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--note-default", default="unknown", help=argparse.SUPPRESS)
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--path", help=argparse.SUPPRESS)
    ap.add_argument("--phase", default="plugged", help=argparse.SUPPRESS)
    ap.add_argument("--run-index", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--json", help=argparse.SUPPRESS)
    return ap.parse_args()


if __name__ == "__main__":
    args = parse()
    if args.child:
        sys.exit(child_main(args))
    if args.selftest:
        sys.exit(selftest())
    main_run(args)
