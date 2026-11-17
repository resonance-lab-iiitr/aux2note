"""Phase 10 / T022: crackle_matrix plan, runner, summary and options. No sound card: the engine,
the recorder and (mostly) crackle_report.run are fakes; sounddevice is never opened."""
import gzip
import os
import tempfile
import types
import unittest

import numpy as np

from tests import _stubs  # noqa: F401
from tools import crackle_matrix as cm

HOSTAPIS = [
    {"name": "MME", "default_input_device": 0, "default_output_device": 1},
    {"name": "Windows DirectSound", "default_input_device": 2, "default_output_device": 3},
    {"name": "Windows WASAPI", "default_input_device": 4, "default_output_device": 5},
]
HOSTAPIS_KS = HOSTAPIS + [{"name": "Windows WDM-KS", "default_input_device": 6, "default_output_device": 7}]


class FakeRecorder:
    def __init__(self, sr, block, seconds=1.0):
        self.sr, self.block = sr, block
        self.seconds = seconds

    def to_files(self, folder, extra_meta=None):
        import soundfile as sf
        os.makedirs(folder, exist_ok=True)
        self.extra_meta = extra_meta
        rng = np.random.default_rng(1)
        sf.write(os.path.join(folder, "raw.wav"), (0.001 * rng.standard_normal(self.sr)).astype(np.float32),
                 self.sr, subtype="FLOAT")
        with gzip.open(os.path.join(folder, "blocks.csv.gz"), "wt") as fh:
            fh.write("index,start,frames,cb_ms,status,adc_time,adc_err_ms,current_time,output_time,t_start\n")
            for i in range(10):
                fh.write("%d,%d,%d,%.3f,0,0,0,0,0,0\n" % (i, i * self.block, self.block, 1.0 + i * 0.1))
        return {}


class FakeEngine:
    instances = []
    fail_when = staticmethod(lambda rate, block, cfg: False)
    fall_back = False

    def __init__(self, rate, block):
        self.sample_rate, self.block_size = rate, block
        self.calls = []
        self.tracks = []
        self.input_monitor_enabled = True
        self.mode_name = "IDLE"
        self.active_config = None
        FakeEngine.instances.append(self)

    def open_stream(self, in_dev, out_dev, cfg):
        self.calls.append(("open", in_dev, out_dev, cfg))
        if FakeEngine.fail_when(self.sample_rate, self.block_size, cfg):
            raise RuntimeError("No audio mode could be opened. Last error: PortAudioError: busy")
        got = cfg
        if FakeEngine.fall_back:
            from dataclasses import replace
            got = replace(cfg, exclusive=False)
        self.active_config = got
        self.mode_name = got.mode_label()
        return got

    def add_track(self, t):
        self.tracks.append(t)

    def set_playhead_seconds(self, s):
        self.calls.append(("playhead", s))

    def play(self):
        self.calls.append(("play",))

    def start_capture(self, max_seconds=120, capture_output=False, **k):
        self.calls.append(("start_capture", capture_output))
        self.rec = FakeRecorder(self.sample_rate, self.block_size)
        return self.rec

    def stop_capture(self):
        self.calls.append(("stop_capture",))
        return self.rec

    def housekeeping(self):
        pass

    def stop(self):
        self.calls.append(("stop",))

    def close_stream(self):
        self.calls.append(("close",))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def fake_report(folder, **kw):
    fake_report.calls.append((folder, kw))
    return {"report": {"counts": {"clicks_per_min": 12.5, "dropouts": 1},
                       "clipping": {"n_samples": 0}, "blocks": {"n_status": 2},
                       "verdict": {"top": "software_scheduling", "confidence": "high"}}}
fake_report.calls = []


class PlanTests(unittest.TestCase):
    def test_default_plan_order_without_wdmks(self):
        plan = cm.build_matrix(HOSTAPIS)
        keys = [(p["key"], p["rate"], p["block"]) for p in plan]
        excl = [(r, b) for r in (44100, 48000) for b in (64, 128, 256, 512)]
        self.assertEqual([(k[1], k[2]) for k in keys if k[0] == "wasapi-excl"], excl)
        self.assertEqual(sorted({k[2] for k in keys if k[0] == "wasapi-excl"}), [64, 128, 256, 512])
        order = []
        for p in plan:
            if p["key"] not in order:
                order.append(p["key"])
        self.assertEqual(order, ["wasapi-excl", "wasapi-shared", "mme", "directsound"])
        for k in ("wasapi-shared", "mme", "directsound"):
            self.assertEqual({(p["rate"], p["block"]) for p in plan if p["key"] == k},
                             {(44100, 256), (48000, 256)})
        self.assertEqual(len(plan), 8 + 2 + 2 + 2)
        self.assertTrue(all(p["exclusive"] for p in plan if p["key"] == "wasapi-excl"))
        self.assertFalse(any(p["exclusive"] for p in plan if p["key"] != "wasapi-excl"))

    def test_wdmks_only_when_present(self):
        self.assertNotIn("wdmks", [p["key"] for p in cm.build_matrix(HOSTAPIS)])
        plan = cm.build_matrix(HOSTAPIS_KS)
        self.assertEqual(plan[-1]["key"], "wdmks")
        self.assertEqual((plan[-1]["in_device"], plan[-1]["out_device"]), (6, 7))

    def test_rates_blocks_and_only_narrow_the_plan(self):
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[128, 256], only=["wasapi-excl", "mme"])
        self.assertEqual([(p["key"], p["rate"], p["block"]) for p in plan],
                         [("wasapi-excl", 48000, 128), ("wasapi-excl", 48000, 256),
                          ("mme", 48000, 128), ("mme", 48000, 256)])

    def test_missing_host_api_is_skipped(self):
        self.assertEqual(cm.build_matrix([HOSTAPIS[0]], only=["wasapi-excl"]), [])

    def test_labels_are_unique(self):
        labels = [p["label"] for p in cm.build_matrix(HOSTAPIS_KS)]
        self.assertEqual(len(labels), len(set(labels)))

    def test_plan_time(self):
        self.assertEqual(cm.plan_seconds(2, 3, 20, wait=False), 2 * 3 * 23)
        self.assertEqual(cm.plan_seconds(2, 3, 20, wait=True), 2 * 3 * 23 + 15)


class OptionTests(unittest.TestCase):
    def test_defaults(self):
        a = cm.parse_args([])
        self.assertEqual((a.seconds, a.scenarios, a.rates, a.blocks, a.apis), (20, ["S1", "S2", "S3", "S4", "S5"], None, None, None))
        self.assertFalse(a.dry_run)

    def test_all_options_parse(self):
        a = cm.parse_args(["--seconds", "5", "--scenarios", "s1,S3", "--out", "x", "--rates", "48000",
                           "--blocks", "128,256", "--apis", "wasapi,mme", "--dry-run", "--yes"])
        self.assertEqual((a.seconds, a.scenarios, a.out, a.rates, a.blocks), (5, ["S1", "S3"], "x", [48000], [128, 256]))
        self.assertEqual(a.apis, ["wasapi-excl", "wasapi-shared", "mme"])
        self.assertTrue(a.dry_run and a.yes)

    def test_quick(self):
        a = cm.parse_args(["--quick"])
        self.assertEqual((a.rates, a.blocks, a.apis), ([48000], [128, 256], ["wasapi-excl", "wasapi-shared", "mme"]))

    def test_bad_values_exit(self):
        for bad in (["--scenarios", "S9"], ["--apis", "alsa"], ["--seconds", "0"]):
            with self.assertRaises(SystemExit):
                cm.parse_args(bad)


class RunTests(unittest.TestCase):
    def setUp(self):
        FakeEngine.instances.clear()
        FakeEngine.fail_when = staticmethod(lambda rate, block, cfg: False)
        FakeEngine.fall_back = False
        fake_report.calls.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, plan, scenarios, seconds=2, **kw):
        return cm.run_matrix(plan, scenarios, seconds, self.tmp.name, FakeEngine, fake_report,
                             wait=False, clock=self.clock, sleep=self.clock.sleep, log=self.logs.append, **kw)

    def test_one_scenario_one_config_gives_a_row_and_a_capture_folder(self):
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[128], only=["wasapi-excl"])
        rows, interrupted = self._run(plan, ["S1"])
        self.assertFalse(interrupted)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["status"], r["clicks_per_min"], r["dropouts"], r["clipping"], r["xruns"]),
                         ("ok", 12.5, 1, 0, 2))
        self.assertEqual(r["verdict"], "software_scheduling (high)")
        self.assertAlmostEqual(r["cb_ms_p99"], 1.891, places=2)
        self.assertEqual(r["folder"], "S1_wasapi-excl_48000_128")
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, r["folder"], "raw.wav")))
        folder, kw = fake_report.calls[0]
        self.assertEqual((kw["effects"], kw["monitoring"], kw["silent_input"], kw["make_png"]), ("off", "off", True, False))
        eng = FakeEngine.instances[0]
        self.assertFalse(eng.input_monitor_enabled)
        self.assertEqual(eng.tracks, [])
        self.assertEqual(eng.calls[-2:], [("stop",), ("close",)])
        self.assertGreaterEqual(self.clock.t, 2)

    def test_tone_scenarios_add_the_tone_track_and_play(self):
        plan = cm.build_matrix(HOSTAPIS, rates=[44100], blocks=[256], only=["mme"])
        self._run(plan, ["S3", "S5"])
        e3, e5 = FakeEngine.instances
        for e in (e3, e5):
            self.assertEqual(len(e.tracks), 1)
            self.assertEqual(e.tracks[0].name, "matrix tone")
            self.assertIn(("play",), e.calls)
            self.assertIn(("start_capture", True), e.calls)
        self.assertIsNone(fake_report.calls[0][1]["silent_input"])      # S3: input is the cable
        self.assertTrue(fake_report.calls[1][1]["silent_input"])        # S5: input ignored

    def test_open_failure_is_recorded_and_the_run_goes_on(self):
        FakeEngine.fail_when = staticmethod(lambda rate, block, cfg: block == 64)
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[64, 128], only=["wasapi-excl"])
        rows, _ = self._run(plan, ["S1"])
        self.assertEqual([r["status"] for r in rows], ["open_failed", "ok"])
        self.assertIn("busy", rows[0]["verdict"])
        self.assertEqual(rows[0]["clicks_per_min"], "")
        self.assertEqual(len(fake_report.calls), 1)
        # the failed engine was still closed
        self.assertIn(("close",), FakeEngine.instances[0].calls)

    def test_fallback_to_another_mode_is_not_counted_as_the_requested_one(self):
        FakeEngine.fall_back = True
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[128], only=["wasapi-excl"])
        rows, _ = self._run(plan, ["S1"])
        self.assertEqual(rows[0]["status"], "fell_back")
        self.assertEqual(fake_report.calls, [])

    def test_no_default_device_is_open_failed(self):
        plan = cm.build_matrix([{"name": "MME", "default_input_device": -1, "default_output_device": 1}])
        rows, _ = self._run(plan, ["S1"])
        self.assertTrue(all(r["status"] == "open_failed" for r in rows))

    def test_scenario_first_configuration_second(self):
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[256], only=["mme", "directsound"])
        rows, _ = self._run(plan, ["S1", "S3"])
        self.assertEqual([(r["scenario"], r["api"]) for r in rows],
                         [("S1", "MME"), ("S1", "Windows DirectSound"), ("S3", "MME"), ("S3", "Windows DirectSound")])

    def test_ctrl_c_returns_the_rows_so_far_and_closes_the_stream(self):
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[128, 256], only=["mme"])
        n = {"i": 0}

        def sleeper(s):
            n["i"] += 1
            if len(FakeEngine.instances) == 2:
                raise KeyboardInterrupt
            self.clock.sleep(s)
        rows, interrupted = cm.run_matrix(plan, ["S1"], 1, self.tmp.name, FakeEngine, fake_report,
                                          wait=False, clock=self.clock, sleep=sleeper, log=self.logs.append)
        self.assertTrue(interrupted)
        self.assertEqual(len(rows), 1)
        self.assertEqual(FakeEngine.instances[1].calls[-2:], [("stop",), ("close",)])
        csv_path, md_path = cm.write_summary(rows, self.tmp.name, ["S1"], 1, interrupted)
        self.assertIn("Stopped early", open(md_path, encoding="utf-8").read())

    def test_real_crackle_report_accepts_the_matrix_arguments(self):
        import crackle_report
        plan = cm.build_matrix(HOSTAPIS, rates=[48000], blocks=[128], only=["mme"])
        rows, _ = cm.run_matrix(plan, ["S1"], 1, self.tmp.name, FakeEngine, crackle_report.run,
                                wait=False, clock=self.clock, sleep=self.clock.sleep, log=self.logs.append)
        self.assertEqual(rows[0]["status"], "ok", rows[0])
        self.assertNotEqual(rows[0]["clicks_per_min"], "")


class SummaryTests(unittest.TestCase):
    def _rows(self, n_cfg=20):
        rows = []
        for sc in cm.SCENARIOS:
            for i in range(n_cfg):
                rows.append(dict(scenario=sc, api="Windows WASAPI", mode="exclusive", rate=48000, block=64 + i,
                                 seconds=20, status="ok" if i % 7 else "open_failed",
                                 clicks_per_min=float(30 - i) if i % 7 else "", dropouts=0, clipping=0,
                                 xruns=0, cb_ms_p99=1.5, verdict="none (low)" if i % 7 else "x", folder="f%d" % i))
        return rows

    def test_csv_and_md_are_written_one_row_per_config_and_scenario(self):
        import csv
        rows = self._rows()
        with tempfile.TemporaryDirectory() as d:
            csv_path, md_path = cm.write_summary(rows, d, list(cm.SCENARIOS), 20)
            with open(csv_path, newline="", encoding="utf-8") as fh:
                got = list(csv.DictReader(fh))
            self.assertEqual(len(got), len(rows))
            self.assertEqual(list(got[0].keys()), cm.SUMMARY_COLUMNS)
            md = open(md_path, encoding="utf-8").read()
        self.assertLessEqual(len(md.splitlines()), 60)
        for sc in cm.SCENARIOS:
            self.assertIn("## " + sc, md)

    def test_md_sorts_by_clicks_and_marks_the_lowest(self):
        rows = self._rows(6)
        md = cm.render_md(rows, ["S1"], 20)
        data = [l for l in md.splitlines() if l.startswith("|") and "clicks/min" not in l and "|-" not in l]
        self.assertTrue(data[0].startswith("| * |"))
        vals = [float(l.split("|")[5]) for l in data]
        self.assertEqual(vals, sorted(vals))

    def test_md_fits_a_page_with_all_five_scenarios_and_a_big_plan(self):
        md = cm.render_md(self._rows(60), list(cm.SCENARIOS), 20)
        self.assertLessEqual(len(md.splitlines()), 60)
        self.assertIn("more in matrix_summary.csv", md)

    def test_scenario_without_finished_runs(self):
        rows = [dict(scenario="S1", api="MME", mode="shared", rate=48000, block=256, seconds=20,
                     status="open_failed", clicks_per_min="", dropouts="", clipping="", xruns="",
                     cb_ms_p99="", verdict="busy", folder="")]
        self.assertIn("No finished run", cm.render_md(rows, ["S1"], 20))


class MainDryRunTests(unittest.TestCase):
    def test_dry_run_prints_the_plan_and_opens_nothing(self):
        import io
        import sys
        import contextlib
        import sounddevice
        opened = []
        orig_stream = sounddevice.Stream
        orig_hostapis = getattr(sounddevice, "query_hostapis", None)
        sounddevice.Stream = lambda *a, **k: opened.append(1)
        sounddevice.query_hostapis = lambda: HOSTAPIS
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = cm.main(["--dry-run", "--seconds", "10", "--scenarios", "S1,S3"])
        finally:
            sounddevice.Stream = orig_stream
            sounddevice.query_hostapis = orig_hostapis
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertEqual(opened, [])
        self.assertIn("14 configurations x 2 scenarios x 10 s = 28 runs", out)
        self.assertIn("Dry run: nothing was opened.", out)
        self.assertIn("wasapi-excl", out)

    def test_bat_file_calls_the_tool_like_the_other_bat_files(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        txt = open(os.path.join(here, "run_crackle_matrix.bat"), encoding="utf-8").read()
        self.assertIn("python tools\\crackle_matrix.py %*", txt)
        self.assertIn('cd /d "%~dp0"', txt)
        self.assertIn("pause", txt)


if __name__ == "__main__":
    unittest.main()
