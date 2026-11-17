"""Phase 10 / T021: the Lab tab (tab_lab.Tab): capture, analyze in a thread, open the folder.
The plain helpers need no Tk; the tab tests build LiveLooperApp under Xvfb with the sounddevice
stub (skipped without a display) and drive the engine callback by hand, no sound card."""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from tests import _stubs  # noqa: F401

try:
    import tkinter as tk
    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


def _feed(engine, seconds, level=0.1):
    """Run `seconds` of quiet noise through the engine callback, block by block."""
    n = engine.block_size
    rng = np.random.RandomState(1)
    for _ in range(int(seconds * engine.sample_rate) // n + 1):
        indata = (level * rng.randn(n, 1)).astype(np.float32)
        outdata = np.zeros((n, 2), dtype=np.float32)
        engine._callback(indata, outdata, n, None, None)


def _fake_result(folder, with_png=True):
    """What crackle_report.run returns, small enough to build by hand."""
    out = os.path.join(folder, "analysis")
    os.makedirs(out, exist_ok=True)
    if with_png:
        from PIL import Image
        Image.new("RGB", (1800, 900), (30, 60, 90)).save(os.path.join(out, "report.png"))
    verdict = {"top": "clean", "confidence": "medium", "summary": "No clicks found.",
               "hypotheses": [{"name": "clean", "evidence": ["no clicks in 20 s", "noise floor -80 dBFS"],
                               "next_test": "try a live source"}], "notes": []}
    rep = {"verdict": verdict, "counts": {"clicks": 0, "clicks_per_min": 0.0, "dropouts": 0, "clip_runs": 0}}
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump(rep, fh)
    return {"out_dir": out, "zip": os.path.join(out, "analysis_pack.zip"), "zip_bytes": 1, "report": rep,
            "verdict": verdict, "files": []}


class PlainHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_safe_label_keeps_only_safe_characters(self):
        import tab_lab
        self.assertEqual(tab_lab.safe_label("My test #1/..\\x"), "My-test-1x")
        self.assertEqual(tab_lab.safe_label("   "), "capture")
        self.assertEqual(tab_lab.safe_label(None), "capture")
        self.assertLessEqual(len(tab_lab.safe_label("a" * 200)), 40)

    def test_capture_folder_name_and_uniqueness(self):
        import tab_lab
        from datetime import datetime
        now = datetime(2026, 11, 11, 15, 30, 5)
        p1 = tab_lab.make_capture_folder(self.tmp, "cable test", now)
        self.assertEqual(os.path.basename(p1), "20261111_153005_cable-test")
        os.makedirs(p1)
        p2 = tab_lab.make_capture_folder(self.tmp, "cable test", now)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p2.endswith("_2"))

    def test_tone_buffer_is_one_second_and_loops_without_a_click(self):
        import tab_lab
        for sr in (44100, 48000):
            b = tab_lab.tone_buffer(sr)
            self.assertEqual(len(b), sr)
            self.assertAlmostEqual(float(np.max(np.abs(b))), tab_lab.TONE_LEVEL, places=3)
            two = np.concatenate([b, b]).astype(np.float64)
            step = np.abs(np.diff(two))
            self.assertLessEqual(step[len(b) - 1], step.max() * 1.0001)   # the seam is no bigger than any step

    def test_list_captures_reads_meta_and_skips_other_folders(self):
        import tab_lab
        a = os.path.join(self.tmp, "20261111_100000_alpha")
        b = os.path.join(self.tmp, "20261111_110000_beta")
        os.makedirs(os.path.join(a, "analysis"))
        os.makedirs(b)
        os.makedirs(os.path.join(self.tmp, "matrix_20261111_120000"))       # no meta, no raw.wav
        with open(os.path.join(a, "meta.json"), "w") as fh:
            json.dump({"label": "alpha", "test_type_name": "Silent input", "seconds": 20.0}, fh)
        with open(os.path.join(a, "analysis", "report.json"), "w") as fh:
            fh.write("{}")
        with open(os.path.join(b, "raw.wav"), "wb") as fh:                   # a bare folder with a wav
            fh.write(b"x")
        rows = tab_lab.list_captures(self.tmp)
        self.assertEqual([r["name"] for r in rows], ["20261111_110000_beta", "20261111_100000_alpha"])
        self.assertTrue(rows[1]["analyzed"])
        self.assertFalse(rows[0]["analyzed"])
        self.assertEqual(rows[1]["type"], "Silent input")
        self.assertEqual(rows[1]["date"], "2026-11-11 10:00:00")
        self.assertEqual(tab_lab.list_captures(os.path.join(self.tmp, "nope")), [])

    def test_evidence_and_counts_text(self):
        import tab_lab
        res = _fake_result(self.tmp, with_png=False)
        lines = tab_lab.evidence_lines(res["verdict"])
        self.assertIn("- no clicks in 20 s", lines)
        self.assertTrue(any(l.startswith("Next test: ") for l in lines))
        self.assertIn("Clicks: 0", tab_lab.counts_line(res["report"]))
        self.assertEqual(tab_lab.evidence_lines(None), [])
        self.assertEqual(tab_lab.counts_line(None), "")


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class LabTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import settings_store
        cls._orig_save = settings_store.save_settings
        settings_store.save_settings = lambda *a, **k: None

    @classmethod
    def tearDownClass(cls):
        import settings_store
        settings_store.save_settings = cls._orig_save

    def setUp(self):
        import ui_theme
        from app import LiveLooperApp
        ui_theme.set_scale(1.0)
        self.tmp = tempfile.mkdtemp()
        self.root = tk.Tk()
        self.app = LiveLooperApp(self.root)
        self.app.cancel_timers()
        self.root.geometry("1366x768")
        self._settle()
        self.tab = self.app.tab_widgets["lab"]
        self.tab.captures_root = self.tmp
        self.engine = self.app.engine
        self.engine.is_active = True              # pretend a stream is open; no sound card needed

    def tearDown(self):
        self.engine.is_active = False
        try:
            self.app.cancel_timers()
            self.app.dlog.close()
        except Exception:
            pass
        self.root.destroy()
        shutil.rmtree(self.tmp, True)

    def _settle(self, n=5):
        for _ in range(n):
            self.root.update_idletasks()
            self.root.update()

    def _wait(self, pred, timeout=20.0):
        end = time.time() + timeout
        while time.time() < end:
            self._settle(1)
            if pred():
                return True
            time.sleep(0.02)
        return False

    def _meta(self, path):
        with open(path) as fh:
            return json.load(fh)

    def _capture(self, type_name="Silent input", label="unit", seconds=5):
        self.tab.type_var.set(type_name)
        self.tab.label_var.set(label)
        self.tab.seconds_var.set(seconds)
        self.tab.start_capture()
        self.assertEqual(self.tab.state, "capturing")
        _feed(self.engine, seconds + 0.5)
        self.assertTrue(self._wait(lambda: self.tab.state == "idle", 5.0))
        return self.tab._last_folder

    # ------------------------------------------------------------------ shell
    def test_lab_is_the_fifth_tab_and_ctrl5_shows_it(self):
        import tabs
        self.assertEqual(tabs.TAB_NAMES[4], "lab")
        self.assertEqual(len(tabs.TAB_NAMES), 5)
        self.assertEqual(len(self.app.notebook.tabs()), 5)
        self.assertEqual(type(self.tab).__module__, "tab_lab")
        self.app.select_tab("lab")
        self._settle()
        self.assertEqual(self.app.current_tab_name(), "lab")
        self.app.select_tab("tracks")
        self._settle()
        self.root.focus_force()
        self.root.event_generate("<Control-Key-5>")
        self._settle()
        self.assertEqual(self.app.current_tab_name(), "lab")

    def test_placeholder_default_exists(self):
        import tabs
        self.assertIn("lab", tabs._DEFAULTS)

    def test_start_is_disabled_until_the_engine_is_mounted(self):
        self.engine.is_active = False
        self.tab.on_tick()
        self.assertIn("disabled", self.tab.start_btn.state())
        self.assertIn("Mount", self.tab.hint_var.get())
        self.engine.is_active = True
        self.tab.on_tick()
        self.assertNotIn("disabled", self.tab.start_btn.state())
        self.assertEqual(self.tab.hint_var.get(), "")
        self.assertIn("disabled", self.tab.stop_btn.state())

    # ------------------------------------------------------------------ capture
    def test_capture_writes_a_folder_with_meta_and_restores_the_engine(self):
        self.engine.input_monitor_enabled = True
        self.app.monitor_var.set(True)
        folder = self._capture("Silent input", "my label", 5)
        self.assertTrue(os.path.isdir(folder))
        self.assertTrue(os.path.basename(folder).endswith("_my-label"))
        for name in ("raw.wav", "blocks.csv.gz", "meta.json"):
            self.assertTrue(os.path.exists(os.path.join(folder, name)), name)
        self.assertFalse(os.path.exists(os.path.join(folder, "output.wav")))
        meta = self._meta(os.path.join(folder, "meta.json"))
        self.assertEqual(meta["test_type"], "silent")
        self.assertEqual(meta["test_type_name"], "Silent input")
        self.assertEqual(meta["label"], "my-label")
        self.assertTrue(meta["silent_input"])
        self.assertTrue(meta["effects_off"] and meta["monitoring_off"])
        self.assertGreaterEqual(meta["seconds"], 5.0)
        self.assertIsNone(self.engine.capture)
        self.assertTrue(self.engine.input_monitor_enabled)          # put back as the user had it
        self.assertTrue(self.app.monitor_var.get())
        self.assertIn("Saved", self.tab.status_var.get())
        self.assertEqual(self.tab._target, folder)
        self.assertEqual(len(self.tab.table.get_children()), 1)
        self.assertNotIn("disabled", self.tab.analyze_btn.state())

    def test_monitoring_is_off_while_capturing(self):
        self.engine.input_monitor_enabled = True
        self.tab.seconds_var.set(5)
        self.tab.start_capture()
        self.assertFalse(self.engine.input_monitor_enabled)
        self.assertIsNotNone(self.engine.capture)
        self.assertIn("disabled", self.tab.start_btn.state())
        self.assertNotIn("disabled", self.tab.stop_btn.state())
        self.tab.stop_capture()
        self.assertTrue(self.engine.input_monitor_enabled)

    def test_stop_ends_a_capture_early(self):
        self.tab.type_var.set("Live source")
        self.tab.seconds_var.set(30)
        self.tab.start_capture()
        _feed(self.engine, 1.0)
        self.tab.stop_capture()
        self.assertEqual(self.tab.state, "idle")
        meta = self._meta(os.path.join(self.tab._last_folder, "meta.json"))
        self.assertLess(meta["seconds"], 5.0)
        self.assertFalse(meta["silent_input"])
        self.assertEqual(meta["test_type"], "live")

    def test_tone_capture_plays_a_tone_track_and_removes_it(self):
        was_playing = self.engine.is_playing
        n_before = len(self.engine.tracks)
        self.tab.type_var.set("Test tone (cable out -> in)")
        self.tab.seconds_var.set(5)
        self.tab.start_capture()
        self.assertEqual(len(self.engine.tracks), n_before + 1)
        tone = self.engine.tracks[-1]
        self.assertTrue(tone.loop_enabled)
        self.assertTrue(self.engine.is_playing)
        _feed(self.engine, 0.5)
        self.assertGreater(tone.peak, 0.05)                         # the tone really reaches the mix
        self.tab.stop_capture()
        self.assertEqual(len(self.engine.tracks), n_before)
        self.assertEqual(self.engine.is_playing, was_playing)
        folder = self.tab._last_folder
        self.assertTrue(os.path.exists(os.path.join(folder, "output.wav")))
        meta = self._meta(os.path.join(folder, "meta.json"))
        self.assertEqual(meta["tone_hz"], 1000.0)
        self.assertFalse(meta["silent_input"])

    def test_playback_only_marks_the_input_as_silent(self):
        self.tab.type_var.set("Playback only")
        self.tab.seconds_var.set(5)
        self.tab.start_capture()
        _feed(self.engine, 0.3)
        self.tab.stop_capture()
        meta = self._meta(os.path.join(self.tab._last_folder, "meta.json"))
        self.assertTrue(meta["silent_input"])
        self.assertEqual(meta["test_type"], "playback")

    def test_duration_is_clamped_and_start_needs_a_mounted_engine(self):
        self.tab.seconds_var.set(1)
        self.tab.start_capture()
        self.assertEqual(self.tab.seconds_var.get(), 5)
        self.assertEqual(self.engine.capture.max_frames, int(round(5 * self.engine.sample_rate)))
        self.tab.stop_capture()
        self.engine.is_active = False
        self.tab.start_capture()
        self.assertEqual(self.tab.state, "idle")
        self.assertIsNone(self.engine.capture)

    # ------------------------------------------------------------------ analysis
    def test_analyze_runs_in_a_background_thread_and_shows_the_result(self):
        folder = self._capture()
        seen = {}

        def slow_run(path, **kw):
            seen["thread"] = threading.current_thread()
            seen["path"], seen["kw"] = path, kw
            time.sleep(0.4)
            return _fake_result(path)

        import crackle_report
        with mock.patch.object(crackle_report, "run", slow_run):
            self.tab.analyze()
            self.assertEqual(self.tab.state, "analyzing")            # returned at once: not blocking
            self.assertIn("disabled", self.tab.analyze_btn.state())
            self.assertIn("disabled", self.tab.start_btn.state())
            self.assertEqual(str(self.tab.an_progress.cget("mode")), "indeterminate")
            self.assertIn("Analyzing", self.tab.verdict_var.get())
            self.assertTrue(self._wait(lambda: self.tab.state == "idle", 10.0))
        self.assertIsNot(seen["thread"], threading.main_thread())
        self.assertEqual(seen["path"], folder)
        self.assertEqual(seen["kw"]["silent_input"], True)
        self.assertEqual(seen["kw"]["effects"], "off")
        self.assertEqual(seen["kw"]["monitoring"], "off")
        self.assertIn("Verdict: clean", self.tab.verdict_var.get())
        self.assertIn("No clicks found.", self.tab.verdict_var.get())
        text = self.tab.evidence.get("1.0", "end")
        self.assertIn("no clicks in 20 s", text)
        self.assertIn("Next test: try a live source", text)
        self.assertIn("Clicks: 0", self.tab.counts_var.get())
        self.assertIsNotNone(self.tab._photo)
        self.assertLessEqual(self.tab._photo.width(), 900)
        self.assertNotEqual(str(self.tab.image_lbl.cget("image")), "")
        self.assertNotIn("disabled", self.tab.analyze_btn.state())
        rows = [self.tab.table.item(i, "values") for i in self.tab.table.get_children()]
        self.assertEqual(rows[0][4], "yes")                           # table refreshed: analyzed

    def test_a_failing_analysis_shows_an_error_and_frees_the_buttons(self):
        self._capture()
        import crackle_report

        def boom(path, **kw):
            raise ValueError("bad wav")

        with mock.patch.object(crackle_report, "run", boom):
            self.tab.analyze()
            self.assertTrue(self._wait(lambda: self.tab.state == "idle", 10.0))
        self.assertIn("Analysis failed", self.tab.verdict_var.get())
        self.assertIn("bad wav", self.tab.verdict_var.get())
        self.assertNotIn("disabled", self.tab.analyze_btn.state())
        self.assertNotIn("disabled", self.tab.start_btn.state())

    def test_real_analysis_of_a_real_capture(self):
        folder = self._capture(seconds=5)
        self.tab.analyze()
        self.assertTrue(self._wait(lambda: self.tab.state == "idle", 90.0))
        an = os.path.join(folder, "analysis")
        self.assertTrue(os.path.exists(os.path.join(an, "report.json")))
        self.assertTrue(os.path.exists(os.path.join(an, "analysis_pack.zip")))
        self.assertIn("Verdict:", self.tab.verdict_var.get())
        self.assertNotIn("failed", self.tab.verdict_var.get())
        self.assertGreater(len(self.tab.evidence.get("1.0", "end").strip()), 0)

    def test_selecting_an_analyzed_capture_shows_its_stored_report(self):
        folder = os.path.join(self.tmp, "20261111_090000_old")
        os.makedirs(folder)
        with open(os.path.join(folder, "meta.json"), "w") as fh:
            json.dump({"label": "old", "seconds": 12.0, "test_type_name": "Live source"}, fh)
        _fake_result(folder)
        self.tab.refresh_list()
        iid = self.tab.table.get_children()[0]
        self.tab.table.selection_set(iid)
        self._settle()
        self.assertEqual(self.tab._target, folder)
        self.assertIn("Verdict: clean", self.tab.verdict_var.get())
        self.assertIsNotNone(self.tab._photo)

    # ------------------------------------------------------------------ open folder, table
    def test_open_folder_button_opens_the_analysis_or_the_capture_folder(self):
        import tab_lab
        folder = os.path.join(self.tmp, "20261111_090000_x")
        os.makedirs(folder)
        self.tab._set_target(folder)
        with mock.patch.object(tab_lab, "open_folder") as op:
            self.tab.open_btn.invoke()
            op.assert_called_once_with(folder)
        os.makedirs(os.path.join(folder, "analysis"))
        with mock.patch.object(tab_lab, "open_folder") as op:
            self.tab.open_btn.invoke()
            op.assert_called_once_with(os.path.join(folder, "analysis"))

    def test_table_refreshes_in_on_show(self):
        self.assertEqual(len(self.tab.table.get_children()), 0)
        d = os.path.join(self.tmp, "20261111_080000_late")
        os.makedirs(d)
        with open(os.path.join(d, "meta.json"), "w") as fh:
            json.dump({"label": "late", "seconds": 7.5, "test_type_name": "Silent input"}, fh)
        self.tab.on_show()
        vals = self.tab.table.item(self.tab.table.get_children()[0], "values")
        self.assertEqual(vals[1], "late")
        self.assertEqual(vals[3], "7.5")
        self.assertEqual(vals[4], "no")

    # ------------------------------------------------------------------ scale, destroy
    def test_scale_change_and_destroy_leave_no_timer_or_error(self):
        self.app.change_ui_scale(+0.2)
        self._settle()
        self.app.change_ui_scale(None)
        self._settle()
        self.assertGreaterEqual(int(self.tab.cap_progress.cget("length")), 300)
        self.tab.seconds_var.set(5)
        self.tab.type_var.set("Playback only")
        self.tab.start_capture()
        self.assertIsNotNone(self.tab._after_id)
        n = len(self.engine.tracks)
        self.tab.destroy()                                           # capture running: cleaned up
        self.assertIsNone(self.tab._after_id)
        self.assertIsNone(self.engine.capture)
        self.assertEqual(len(self.engine.tracks), n - 1)
        self._settle()


if __name__ == "__main__":
    unittest.main()
