"""Phase 6 tests: ring buffer, file log, rt counters, report, exception hook,
test signal, Debug Center smoke test (skipped without Tk)."""
import os
import sys
import tempfile
import unittest

import numpy as np

from tests import _stubs  # noqa: F401
from tests.fake_stream import make_engine, run_blocks, sine
import debug_log as dl


def mk(**kw):
    return dl.DebugLog(log_dir=tempfile.mkdtemp(), **kw)


class RingAndFile(unittest.TestCase):
    def test_ring_limit(self):
        d = mk(ring_size=50)
        for i in range(120):
            d.add(f"line {i}", "SYS")
        self.assertEqual(len(d.ring), 50)
        self.assertIn("line 119", d.last_lines(1)[0])
        d.close()

    def test_levels_and_search(self):
        d = mk()
        d.add("probe", "PROBE"); d.add("hello", "SYS"); d.add("careful", "WARN")
        d.add("bad", "ERROR"); d.add("worse", "CRIT")
        self.assertEqual([r[1] for r in d.ring], ["DEBUG", "INFO", "WARN", "ERROR", "CRIT"])
        self.assertEqual(len(d.records("WARN")), 3)
        self.assertEqual(len(d.records("DEBUG", "HELLO")), 1)
        self.assertEqual(len(d.records("ERROR", "hello")), 0)
        d.close()

    def test_file_written(self):
        d = mk()
        d.add("to file", "SYS")
        d.close()
        with open(os.path.join(d.log_dir, "looper.log"), encoding="utf-8") as fh:
            txt = fh.read()
        self.assertIn("to file", txt)

    def test_bad_dir_does_not_crash(self):
        d = dl.DebugLog(log_dir=os.path.join(tempfile.mkdtemp(), "x\0y"))
        d.add("still works", "SYS")
        self.assertEqual(len(d.ring), 1)

    def test_rt_counter_becomes_one_line(self):
        d = mk()
        for _ in range(5):
            d.log_rt("PortAudio status flag")
        self.assertEqual(len(d.drain_rt()), 1)
        self.assertEqual(d.drain_rt(), [])
        d.log_rt("PortAudio status flag")
        self.assertEqual(len(d.drain_rt()), 1)
        d.close()


class Report(unittest.TestCase):
    def test_sections(self):
        e = make_engine()
        d = mk()
        for i in range(150):
            d.add(f"msg {i}", "SYS")
        e.set_calibration(8.5, key="WASAPI EXCL 48000/64")
        txt = dl.build_report(e, {"driver": "WASAPI", "block_size": 64}, d)
        for sec in ("== VERSIONS ==", "== SETTINGS ==", "== ENGINE ==", "== TELEMETRY ==",
                    "== CALIBRATION ==", "== LAST 100 LOG LINES =="):
            self.assertIn(sec, txt)
        self.assertIn("driver: WASAPI", txt)
        self.assertIn("RTT 8.50 ms", txt)
        self.assertIn("msg 149", txt)
        self.assertNotIn("msg 49\n", txt)
        path = dl.save_report(txt, d.log_dir)
        self.assertTrue(os.path.exists(path))
        d.close()

    def test_snapshots(self):
        from track import Track
        e = make_engine()
        t = Track("T1", 48000)
        t.effects.delay.enabled = True
        e.add_track(t)
        rows = dict(dl.engine_snapshot(e))
        self.assertEqual(rows["tracks"], 1)
        tr = dl.tracks_snapshot(e, {"delay": 3.0})
        self.assertEqual(tr[0][0], "T1")
        self.assertIn("delay", tr[0][3])
        self.assertEqual(tr[0][4], 3.0)


class Exceptions(unittest.TestCase):
    def test_handler_logs_and_notifies(self):
        d = mk()
        seen = []
        try:
            raise ValueError("boom")
        except ValueError:
            dl.handle_exception(d, *sys.exc_info(), where="test", notify=lambda t, m: seen.append(m))
        self.assertTrue(any(r[1] == "CRIT" and "boom" in r[2] for r in d.ring))
        self.assertTrue(any("Traceback" in r[2] for r in d.ring))
        self.assertIn("boom", seen[0])
        d.close()

    def test_handler_never_raises(self):
        dl.handle_exception(None, ValueError, ValueError("x"), None)   # broken logger

    def test_hooks_installed(self):
        old = sys.excepthook
        try:
            d = mk()
            dl.install_exception_hooks(d)
            self.assertIsNot(sys.excepthook, old)
            d.close()
        finally:
            sys.excepthook = old


class TestSignalTests(unittest.TestCase):
    def test_sine_and_off(self):
        e = make_engine()
        e.set_test_signal("sine", 0.2)
        l, r = run_blocks(e, np.zeros(6400, dtype=np.float32))
        self.assertAlmostEqual(float(np.max(np.abs(l))), 0.2, delta=0.01)
        np.testing.assert_array_equal(l, r)
        self.assertAlmostEqual(e.peak_l, 0.2, delta=0.01)
        e.set_test_signal(None)
        l, _ = run_blocks(e, np.zeros(640, dtype=np.float32))
        self.assertEqual(float(np.max(np.abs(l))), 0.0)

    def test_noise_and_level_clamp(self):
        e = make_engine()
        e.set_test_signal("noise", 5.0)           # clamped to 0.5
        l, _ = run_blocks(e, np.zeros(6400, dtype=np.float32))
        self.assertTrue(0.1 < float(np.max(np.abs(l))) <= 0.5)
        with self.assertRaises(ValueError):
            e.set_test_signal("saw")

    def test_phase_is_continuous(self):
        e = make_engine()
        e.set_test_signal("sine", 0.3)
        l, _ = run_blocks(e, np.zeros(48000 + 640, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.3 * 2 * np.pi * 440 / 48000 * 1.05)

    def test_close_stops_test(self):
        e = make_engine()
        e.set_test_signal("sine")
        e.close_stream()
        self.assertIsNone(e.test_signal_name)

    def test_xrun_status_counted_by_rt(self):
        e = make_engine()
        d = mk()
        e.debug_rt = d

        class S:
            input_underflow = True
        e._callback(np.zeros((64, 1), np.float32), np.zeros((64, 2), np.float32), 64, None, S())
        self.assertEqual(len(d.drain_rt()), 1)
        d.close()


class GuiSmoke(unittest.TestCase):
    def test_debug_center(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception:
            self.skipTest("no Tk / display here (runs on the PC)")
        from debug_center import DebugCenter
        e = make_engine()
        d = mk()
        rows = [{"id": 1, "driver": "WASAPI", "max_in": 1, "max_out": 2,
                 "default_sr": 48000.0, "name": "Mic"}]
        dc = DebugCenter(root, d, e, lambda: {"driver": "WASAPI"}, lambda: rows, lambda: None)
        d.add("hello", "SYS"); d.add("oops", "ERROR")
        dc.pump()
        self.assertIn("hello", dc.console.get("1.0", "end"))
        dc.level_var.set("ERROR"); dc.rerender()
        self.assertNotIn("hello", dc.console.get("1.0", "end"))
        for i in range(4):
            dc.nb.select(i); dc.refresh()
        self.assertEqual(len(dc.dev_tree.get_children()), 1)
        txt = dc.copy_report()
        self.assertIn("== ENGINE ==", txt)
        self.assertIn("== ENGINE ==", root.clipboard_get())
        dc.toggle_test_bar(); dc.toggle_test()      # not mounted -> warning, no crash
        self.assertIsNone(e.test_signal_name)
        root.destroy(); d.close()


if __name__ == "__main__":
    unittest.main()
