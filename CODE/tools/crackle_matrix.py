"""
tools/crackle_matrix.py  (Phase 10, T022)

Runs the SAME captures in every driver / mode / sample rate / block size and writes one
summary table, so you can see whether the crackle depends on the engine mode.

    python tools\\crackle_matrix.py --dry-run          # print the plan and the total time
    python tools\\crackle_matrix.py --quick            # blocks 128 + 256, 48000 Hz, WASAPI + MME
    python tools\\crackle_matrix.py --scenarios S1,S3 --seconds 20 --apis wasapi-excl,mme

Scenarios (effects off, monitoring off, no CLEAN INPUT in the capture: raw.wav is the exact
card input):
    S1  silence: nothing plugged into the input, no tracks.
    S2  line-in with a muted source (source connected, volume at zero), no tracks.
    S3  1 kHz test tone played by the app; cable from the output to the input.
    S4  live source: play music into the input, monitoring off, no tracks.
    S5  same tone as S3, but the input is ignored (the capture still records the timing).

Order: scenario first, configuration second, so cables are changed as rarely as possible.
Captures go to captures/matrix_<YYYYMMDD_HHMMSS>/ next to main.py (never in the zip).
"""
import argparse
import csv
import datetime
import gzip
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from stream_config import StreamConfig, WASAPI_NAME  # noqa: E402

TONE_HZ = 1000.0
TONE_LEVEL = 0.3
DEFAULT_SECONDS = 20
DEFAULT_RATES = (44100, 48000)
EXCLUSIVE_BLOCKS = (64, 128, 256, 512)
SHARED_BLOCKS = (256,)
QUICK_BLOCKS = (128, 256)
QUICK_RATES = (48000,)
QUICK_APIS = ("wasapi-excl", "wasapi-shared", "mme")
WAIT_SECONDS = 5
OPEN_CLOSE_SECONDS = 3          # rough time to open, start and close one stream

API_KEYS = ("wasapi-excl", "wasapi-shared", "mme", "directsound", "wdmks")

# scenario: (title, instruction, tone, silent_input)
SCENARIOS = {
    "S1": ("silence", "Unplug everything from the input (or cover the mic). Stay quiet.", False, True),
    "S2": ("muted line-in", "Connect the source to line-in, volume at ZERO.", False, True),
    "S3": ("tone loopback", "Cable from the output to the input, Windows volume LOW.", True, False),
    "S4": ("live source", "Play music or your instrument into the input. Monitoring stays off.", False, False),
    "S5": ("tone, input ignored", "Same tone as S3; unplug the input cable.", True, True),
}
SUMMARY_COLUMNS = ["scenario", "api", "mode", "rate", "block", "seconds", "status", "clicks_per_min",
                   "dropouts", "clipping", "xruns", "cb_ms_p99", "verdict", "folder"]
MAX_MD_LINES = 60


# ----------------------------------------------------------------------------
# Plan
# ----------------------------------------------------------------------------
def api_key_of(name):
    """Host API name -> short key (wasapi / mme / directsound / wdmks) or None."""
    n = str(name).lower()
    if "wasapi" in n:
        return "wasapi"
    if "directsound" in n:
        return "directsound"
    if "wdm" in n:
        return "wdmks"
    if "mme" in n:
        return "mme"
    return None


def _label(api_short, rate, block):
    return "%s_%d_%d" % (api_short, rate, block)


def build_matrix(hostapis, rates=None, blocks=None, only=None):
    """The list of configurations to run, in order: WASAPI exclusive at 64/128/256/512, WASAPI
    shared, MME, DirectSound, WDM-KS (only when the host API list has it), each at 44100 and
    48000 Hz. `blocks` narrows the block sizes (then used for every mode); `only` is a list of
    API_KEYS. Each entry is a dict: key, api, exclusive, rate, block, label, in_device,
    out_device."""
    rates = tuple(rates) if rates else DEFAULT_RATES
    by_key = {}
    for api in hostapis or []:
        k = api_key_of(api.get("name", ""))
        if k and k not in by_key:
            by_key[k] = api
    plan = []

    def add(key, api_key, exclusive, short, blocklist):
        api = by_key.get(api_key)
        if api is None:
            return
        if only and key not in only:
            return
        for rate in rates:
            for block in blocklist:
                plan.append(dict(key=key, api=api["name"], exclusive=exclusive, rate=int(rate),
                                 block=int(block), label=_label(short, rate, block),
                                 in_device=api.get("default_input_device"),
                                 out_device=api.get("default_output_device")))

    excl_blocks = tuple(blocks) if blocks else EXCLUSIVE_BLOCKS
    other_blocks = tuple(blocks) if blocks else SHARED_BLOCKS
    add("wasapi-excl", "wasapi", True, "wasapi-excl", excl_blocks)
    add("wasapi-shared", "wasapi", False, "wasapi-shared", other_blocks)
    add("mme", "mme", False, "mme", other_blocks)
    add("directsound", "directsound", False, "ds", other_blocks)
    add("wdmks", "wdmks", False, "wdmks", other_blocks)
    return plan


def plan_seconds(n_configs, n_scenarios, seconds, wait=True):
    """Total run time in seconds: every run + open / close, plus the wait before a scenario."""
    return n_configs * n_scenarios * (seconds + OPEN_CLOSE_SECONDS) + (WAIT_SECONDS * n_scenarios if wait else 0)


def fmt_duration(s):
    s = int(round(s))
    return "%d min %02d s" % (s // 60, s % 60)


# ----------------------------------------------------------------------------
# One run
# ----------------------------------------------------------------------------
def tone_buffer(sample_rate):
    """One second of a 1 kHz sine (a whole number of cycles at 44100 and 48000 Hz)."""
    n = int(sample_rate)
    t = np.arange(n, dtype=np.float64) / float(sample_rate)
    return (TONE_LEVEL * np.sin(2.0 * np.pi * TONE_HZ * t)).astype(np.float32)


def _blank_row(scenario, cfg, seconds, status, error=""):
    return dict(scenario=scenario, api=cfg["api"], mode="exclusive" if cfg["exclusive"] else "shared",
                rate=cfg["rate"], block=cfg["block"], seconds=seconds, status=status,
                clicks_per_min="", dropouts="", clipping="", xruns="", cb_ms_p99="",
                verdict=error, folder="")


def _cb_p99(folder):
    try:
        with gzip.open(os.path.join(folder, "blocks.csv.gz"), "rt") as fh:
            head = fh.readline().strip().split(",")
            data = np.genfromtxt(fh, delimiter=",", ndmin=2)
        if data.size == 0 or "cb_ms" not in head:
            return ""
        col = np.atleast_2d(data)[:, head.index("cb_ms")]
        col = col[np.isfinite(col)]
        return round(float(np.percentile(col, 99)), 3) if col.size else ""
    except Exception:
        return ""


def run_one(scenario, cfg, seconds, out_dir, engine_factory, report_run, clock=time.time,
            sleep=time.sleep, log=print):
    """Open one configuration, run one scenario, analyse it. Returns a summary row (dict).
    Never raises for a stream that cannot be opened: that is a row with status open_failed."""
    title, _instr, tone, silent = SCENARIOS[scenario]
    if cfg.get("in_device") is None or cfg.get("out_device") is None \
            or cfg["in_device"] < 0 or cfg["out_device"] < 0:
        return _blank_row(scenario, cfg, seconds, "open_failed", "no default input / output device")
    eng = engine_factory(cfg["rate"], cfg["block"])
    scfg = StreamConfig(api=cfg["api"], exclusive=cfg["exclusive"], sample_rate=cfg["rate"],
                        block_size=cfg["block"])
    try:
        try:
            eng.open_stream(cfg["in_device"], cfg["out_device"], scfg)
        except RuntimeError as e:
            return _blank_row(scenario, cfg, seconds, "open_failed", str(e)[:200])
        except Exception as e:                                   # PortAudio errors and the like
            return _blank_row(scenario, cfg, seconds, "open_failed", "%s: %s" % (type(e).__name__, e))
        got = getattr(eng, "active_config", None)
        if got is not None and (got.sample_rate != cfg["rate"] or got.exclusive != cfg["exclusive"]
                                or got.block_size != cfg["block"]):
            return _blank_row(scenario, cfg, seconds, "fell_back",
                              "opened as %s instead" % getattr(eng, "mode_name", "?"))
        eng.input_monitor_enabled = False
        if tone:
            from track import Track
            tr = Track("matrix tone", eng.sample_rate)
            tr.load_from_array(tone_buffer(eng.sample_rate), 0)
            tr.loop_enabled = True
            eng.add_track(tr)
            eng.set_playhead_seconds(0)
            eng.play()
        eng.start_capture(max_seconds=int(seconds) + 5, capture_output=bool(tone))
        end = clock() + seconds
        while clock() < end:
            eng.housekeeping()
            sleep(0.1)
        rec = eng.stop_capture()
        folder = os.path.join(out_dir, "%s_%s" % (scenario, cfg["label"]))
        extra = {"scenario": scenario, "scenario_title": title, "effects_off": True,
                 "monitoring_off": True, "silent_input": bool(silent),
                 "engine_mode": str(getattr(eng, "mode_name", "")), "api": cfg["api"],
                 "matrix": True}
        rec.to_files(folder, extra_meta=extra)
        res = report_run(folder, effects="off", monitoring="off",
                         silent_input=True if silent else None, make_png=False)
        rep = res["report"]
        counts, blocks = rep.get("counts", {}), rep.get("blocks", {})
        row = _blank_row(scenario, cfg, seconds, "ok")
        row.update(clicks_per_min=counts.get("clicks_per_min", ""), dropouts=counts.get("dropouts", ""),
                   clipping=rep.get("clipping", {}).get("n_samples", ""),
                   xruns=blocks.get("n_status", ""), cb_ms_p99=_cb_p99(folder),
                   verdict=(rep.get("verdict", {}).get("top", "") + " (" +
                            str(rep.get("verdict", {}).get("confidence", "")) + ")").strip(),
                   folder=os.path.basename(folder))
        return row
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log("  run failed: %s: %s" % (type(e).__name__, e))
        return _blank_row(scenario, cfg, seconds, "run_failed", "%s: %s" % (type(e).__name__, e))
    finally:
        try:
            eng.stop()
        except Exception:
            pass
        try:
            eng.close_stream()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Summary files
# ----------------------------------------------------------------------------
def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SUMMARY_COLUMNS})


def _num(v):
    return v if isinstance(v, (int, float)) else float("inf")


def render_md(rows, scenarios, seconds, interrupted=False):
    """One page (at most MAX_MD_LINES lines): per scenario the configurations with the fewest
    clicks per minute first (the lowest is marked *), failures counted in one line."""
    lines = ["# Crackle matrix", ""]
    lines.append("Seconds per run: %s. Clicks/min = clicks found in raw.wav by crackle_core "
                 "(hypothesis, not proof)." % seconds)
    if interrupted:
        lines.append("**Stopped early (Ctrl+C): only the runs that finished are listed.**")
    lines.append("")
    n_sc = max(1, len(scenarios))
    per = max(3, (MAX_MD_LINES - len(lines) - 6 * n_sc) // n_sc)
    for sc in scenarios:
        mine = [r for r in rows if r["scenario"] == sc]
        ok = sorted([r for r in mine if r["status"] == "ok"], key=lambda r: _num(r["clicks_per_min"]))
        bad = [r for r in mine if r["status"] != "ok"]
        lines.append("## %s %s" % (sc, SCENARIOS[sc][0]))
        if not ok:
            lines.append("No finished run.%s" % (" %d not opened." % len(bad) if bad else ""))
            lines.append("")
            continue
        lines.append("| | mode | rate | block | clicks/min | drop | xruns | p99 ms | verdict |")
        lines.append("|-|-|-|-|-|-|-|-|-|")
        for i, r in enumerate(ok[:per]):
            lines.append("| %s | %s %s | %s | %s | %s | %s | %s | %s | %s |" % (
                "*" if i == 0 else "", str(r["api"]).replace("Windows ", ""), r["mode"], r["rate"],
                r["block"], r["clicks_per_min"], r["dropouts"], r["xruns"], r["cb_ms_p99"], r["verdict"]))
        tail = []
        if len(ok) > per:
            tail.append("%d more in matrix_summary.csv" % (len(ok) - per))
        if bad:
            tail.append("%d not run (open_failed / fell_back / run_failed)" % len(bad))
        if tail:
            lines.append("(" + "; ".join(tail) + ")")
        lines.append("")
    return "\n".join(lines[:MAX_MD_LINES]) + "\n"


def write_summary(rows, out_dir, scenarios, seconds, interrupted=False):
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "matrix_summary.csv")
    md_path = os.path.join(out_dir, "matrix_summary.md")
    write_csv(rows, csv_path)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_md(rows, scenarios, seconds, interrupted))
    return csv_path, md_path


# ----------------------------------------------------------------------------
# Whole matrix
# ----------------------------------------------------------------------------
def run_matrix(plan, scenarios, seconds, out_dir, engine_factory, report_run, wait=True,
               input_fn=None, clock=time.time, sleep=time.sleep, log=print):
    """Scenario first, configuration second. Returns (rows, interrupted). Ctrl+C stops the loop;
    the rows finished so far are returned (the caller writes the summary)."""
    rows = []
    try:
        for sc in scenarios:
            title, instr, _tone, _silent = SCENARIOS[sc]
            log("\n=== %s: %s ===\n%s" % (sc, title, instr))
            if wait:
                if input_fn is not None:
                    input_fn("Press ENTER when ready (or wait %d s)... " % WAIT_SECONDS)
                else:
                    sleep(WAIT_SECONDS)
            for i, cfg in enumerate(plan, 1):
                log("[%s %d/%d] %s %s %d Hz / %d" % (sc, i, len(plan), cfg["api"],
                                                     "exclusive" if cfg["exclusive"] else "shared",
                                                     cfg["rate"], cfg["block"]))
                row = run_one(sc, cfg, seconds, out_dir, engine_factory, report_run,
                              clock=clock, sleep=sleep, log=log)
                log("   -> %s%s" % (row["status"], (" " + str(row["verdict"])) if row["status"] != "ok" else
                                    " clicks/min %s" % row["clicks_per_min"]))
                rows.append(row)
    except KeyboardInterrupt:
        log("\nStopped early (Ctrl+C).")
        return rows, True
    return rows, False


# ----------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------
def _int_list(text):
    return [int(x) for x in str(text).replace(";", ",").split(",") if x.strip()]


def _name_list(text):
    return [x.strip() for x in str(text).split(",") if x.strip()]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Run the crackle captures in every driver / mode / rate / block size.",
        epilog="Real-card behaviour (which drivers open, PortAudio status flags, time_info) is only "
               "checked on your own PC (task T024). Captures go to captures/matrix_<time>/ next "
               "to main.py.")
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS, help="length of each run (default 20)")
    ap.add_argument("--scenarios", default="S1,S2,S3,S4,S5", help="comma list, e.g. S1,S3")
    ap.add_argument("--out", default=None, help="output folder (default captures/matrix_<time>)")
    ap.add_argument("--rates", default=None, help="comma list, e.g. 48000 (default 44100,48000)")
    ap.add_argument("--blocks", default=None, help="comma list, e.g. 128,256 (default: see --help text above)")
    ap.add_argument("--apis", default=None,
                    help="comma list of: " + ", ".join(API_KEYS) + " (wasapi = both WASAPI modes)")
    ap.add_argument("--quick", action="store_true", help="blocks 128 and 256, 48000 Hz, WASAPI + MME only")
    ap.add_argument("--yes", action="store_true", help="do not wait before each scenario")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the total time, open nothing")
    a = ap.parse_args(argv)

    sc = [s.upper() for s in _name_list(a.scenarios)]
    bad = [s for s in sc if s not in SCENARIOS]
    if bad or not sc:
        ap.error("unknown scenario %s (use S1..S5)" % ", ".join(bad or ["(none)"]))
    a.scenarios = sc
    a.rates = _int_list(a.rates) if a.rates else None
    a.blocks = _int_list(a.blocks) if a.blocks else None
    apis = _name_list(a.apis.lower()) if a.apis else None
    if apis:
        expanded = []
        for k in apis:
            expanded += ["wasapi-excl", "wasapi-shared"] if k == "wasapi" else [k]
        unknown = [k for k in expanded if k not in API_KEYS]
        if unknown:
            ap.error("unknown --apis value %s (use %s)" % (", ".join(unknown), ", ".join(API_KEYS)))
        apis = expanded
    if a.quick:
        a.rates = a.rates or list(QUICK_RATES)
        a.blocks = a.blocks or list(QUICK_BLOCKS)
        apis = apis or list(QUICK_APIS)
    a.apis = apis
    if a.seconds <= 0:
        ap.error("--seconds must be positive")
    return a


def main(argv=None):
    args = parse_args(argv)
    import sounddevice as sd
    hostapis = [dict(h) for h in sd.query_hostapis()]
    plan = build_matrix(hostapis, args.rates, args.blocks, args.apis)
    total = plan_seconds(len(plan), len(args.scenarios), args.seconds, wait=not args.yes)
    print("Crackle matrix: %d configurations x %d scenarios x %g s = %d runs, about %s."
          % (len(plan), len(args.scenarios), args.seconds, len(plan) * len(args.scenarios), fmt_duration(total)))
    if not plan:
        print("No matching host API found on this PC.")
        return 1
    if args.dry_run:
        for sc in args.scenarios:
            print("%s  %s" % (sc, SCENARIOS[sc][0]))
        for cfg in plan:
            print("   %-14s %-9s %5d Hz  block %3d   %s" % (
                cfg["key"], "exclusive" if cfg["exclusive"] else "shared", cfg["rate"], cfg["block"], cfg["label"]))
        print("Dry run: nothing was opened.")
        return 0

    from audio_engine import AudioEngine
    import crackle_report
    out_dir = args.out or os.path.join(ROOT, "captures", "matrix_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    factory = lambda rate, block: AudioEngine(sample_rate=rate, block_size=block)  # noqa: E731
    rows, interrupted = [], False
    try:
        rows, interrupted = run_matrix(plan, args.scenarios, args.seconds, out_dir, factory,
                                       crackle_report.run, wait=not args.yes, input_fn=None)
    finally:
        csv_path, md_path = write_summary(rows, out_dir, args.scenarios, args.seconds, interrupted)
        print("\nSummary: %s\n         %s" % (md_path, csv_path))
    return 130 if interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
