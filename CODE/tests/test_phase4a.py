"""Phase 4a tests: telemetry math, xrun counting, engine hook, status text."""
import types
import unittest
import numpy as np

from tests.fake_stream import make_engine, run_blocks, sine
from telemetry import Telemetry, format_status, short_mode, load_color
from stream_config import StreamConfig

SR = 48000
BLK = 64


class TelemetryMath(unittest.TestCase):
    def test_cpu_percent(self):
        t = Telemetry()
        block_s = BLK / SR
        for _ in range(200):
            t.record(0.0, block_s * 0.30, BLK, SR)
        self.assertAlmostEqual(t.cpu_load(), 0.30, places=3)
        self.assertAlmostEqual(t.peak_load(), 0.30, places=3)
        self.assertEqual(t.overruns, 0)

    def test_overrun_and_max(self):
        t = Telemetry()
        block_s = BLK / SR
        t.record(0.0, block_s * 0.2, BLK, SR)
        t.record(0.0, block_s * 1.5, BLK, SR)
        self.assertEqual(t.overruns, 1)
        self.assertAlmostEqual(t.peak_load(), 1.5, places=3)

    def test_xruns_from_status_flags(self):
        t = Telemetry()
        ok = types.SimpleNamespace(input_underflow=False, output_underflow=False,
                                   input_overflow=False, output_overflow=False)
        bad = types.SimpleNamespace(input_underflow=False, output_underflow=True,
                                    input_overflow=True, output_overflow=False)
        t.record(0, 0.0001, BLK, SR, ok)
        t.record(0, 0.0001, BLK, SR, bad)
        t.record(0, 0.0001, BLK, SR, None)
        self.assertEqual(t.xruns, 1)           # one bad block counts once
        self.assertEqual(t.output_underflow, 1)
        self.assertEqual(t.input_overflow, 1)

    def test_history_is_oldest_first_and_fixed_length(self):
        t = Telemetry(history=10)
        block_s = BLK / SR
        for i in range(25):
            t.record(0.0, block_s * (i + 1) / 100.0, BLK, SR)
        h = t.history_loads()
        self.assertEqual(len(h), 10)
        self.assertTrue(np.all(np.diff(h) > 0))   # oldest first
        self.assertAlmostEqual(h[-1], 0.25, places=3)

    def test_reset(self):
        t = Telemetry()
        t.record(0, 0.001, BLK, SR)
        t.reset()
        self.assertEqual(t.blocks, 0)
        self.assertEqual(t.cpu_load(), 0.0)
        self.assertEqual(float(t.history_loads().sum()), 0.0)

    def test_summary_keys(self):
        s = Telemetry().summary()
        for k in ("cpu_avg_pct", "cpu_peak_pct", "xruns", "overruns", "block_ms"):
            self.assertIn(k, s)


class EngineHook(unittest.TestCase):
    def test_callback_fills_telemetry(self):
        e = make_engine(SR, BLK)
        run_blocks(e, sine(SR // 2, SR))
        self.assertEqual(e.telemetry.blocks, (SR // 2) // BLK)
        self.assertGreater(e.telemetry.last_s, 0.0)
        self.assertAlmostEqual(e.telemetry.block_s, BLK / SR, places=9)
        self.assertGreaterEqual(e.cpu_load(), 0.0)

    def test_callback_does_not_log_on_status(self):
        """A status flag must be counted, never logged from the audio thread."""
        lines = []
        e = make_engine(SR, BLK)
        e._log = lambda *a, **k: lines.append(a)
        bad = types.SimpleNamespace(input_underflow=True, output_underflow=False,
                                    input_overflow=False, output_overflow=False)
        indata = np.zeros((BLK, 1), dtype=np.float32)
        outdata = np.zeros((BLK, 2), dtype=np.float32)
        e._callback(indata, outdata, BLK, None, bad)
        self.assertEqual(lines, [])
        self.assertEqual(e.telemetry.xruns, 1)

    def test_pa_cpu_load_without_stream(self):
        self.assertIsNone(make_engine().pa_cpu_load())


class StatusText(unittest.TestCase):
    def test_idle_text(self):
        e = make_engine()
        self.assertEqual(short_mode(e), "IDLE")

    def test_exclusive_text(self):
        e = make_engine()
        e.active_config = StreamConfig(exclusive=True, sample_rate=48000, block_size=64)
        run_blocks(e, sine(SR // 4, SR))
        text = format_status(e)
        self.assertTrue(text.startswith("WASAPI EXCL 48000/64 | RTT "))
        for part in ("(reported, not measured)", "CPU ", "xruns 0", "peak "):
            self.assertIn(part, text)

    def test_shared_text(self):
        e = make_engine()
        e.active_config = StreamConfig(exclusive=False, sample_rate=48000, block_size=128)
        self.assertEqual(short_mode(e), "SHARED 48000/128")

    def test_colors(self):
        self.assertEqual(load_color(0.2, 0.1), "#00FF66")
        self.assertEqual(load_color(0.8, 0.1), "#FF3333")
        self.assertEqual(load_color(0.2, 0.95), "#FF3333")


if __name__ == "__main__":
    unittest.main()
