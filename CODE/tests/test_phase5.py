"""Phase 5 tests: latency calibration against a simulated loopback cable."""
import threading
import time
import unittest

import numpy as np

from tests import _stubs  # noqa: F401
import latency_core as lc
import settings_store as ss
from stream_config import StreamConfig
from telemetry import rtt_text, format_status
from tests.fake_stream import make_engine


def loopback(engine, delay, gain=1.0, noise=0.0, block=64, realtime=False):
    """Drive engine._callback like PortAudio, with the output fed back to the
    input after `delay` samples (the Line Out -> Line In cable)."""
    rng = np.random.default_rng(1)
    hist = np.zeros(delay + block, dtype=np.float32)   # past output (left ch)
    n = 0
    while engine._calib is not None and not engine._calib.done:
        outdata = np.zeros((block, 2), dtype=np.float32)
        # input = what was played `delay` samples ago
        idx = np.arange(n, n + block) - delay
        indata = np.zeros((block, 1), dtype=np.float32)
        ok = idx >= 0
        indata[ok, 0] = engine._loop_out[idx[ok]] if hasattr(engine, "_loop_out") else 0
        indata[:, 0] = np.clip(indata[:, 0] * gain + rng.normal(0, noise, block), -1, 1)
        engine._callback(indata, outdata, block, None, None)
        engine._loop_out = np.concatenate([getattr(engine, "_loop_out", np.zeros(0, np.float32)), outdata[:, 0]])
        n += block
        if realtime:
            time.sleep(0)


class FakeStreamObj:
    latency = (0.0, 0.0)
    cpu_load = 0.0


def run_cal(delay, gain=1.0, noise=0.0, sr=48000, level=lc.DEFAULT_LEVEL):
    e = make_engine(sr, 64)
    e.is_active = True
    e.stream = FakeStreamObj()
    e.active_config = StreamConfig(sample_rate=sr, block_size=64)
    out = {}
    t = threading.Thread(target=lambda: out.update(r=e.run_calibration(level=level)))
    t.start()
    while e._calib is None and t.is_alive():
        time.sleep(0.001)
    loopback(e, delay, gain, noise)
    t.join(10)
    return e, out["r"]


class CalibrationTests(unittest.TestCase):
    def test_known_delay_within_one_sample(self):
        e, r = run_cal(400)
        self.assertEqual(r["status"], lc.STATUS_OK)
        self.assertLessEqual(abs(r["rtt_samples"] - 400), 1)
        self.assertAlmostEqual(r["rtt_ms"], 400 / 48.0, delta=1 / 48.0)
        self.assertLess(r["jitter_ms"], 0.05)

    def test_44100_rate(self):
        e, r = run_cal(333, sr=44100)
        self.assertEqual(r["status"], lc.STATUS_OK)
        self.assertLessEqual(abs(r["rtt_samples"] - 333), 1)

    def test_result_stored_and_applied(self):
        e, r = run_cal(400)
        self.assertLessEqual(abs(e.record_latency_samples - 400), 1)
        self.assertEqual(e.calibration["key"], "WASAPI EXCL 48000/64")
        self.assertIsNotNone(e.measured_rtt_ms())
        self.assertIn("(measured)", rtt_text(e))
        self.assertIsNone(e._calib)               # looper mix is back

    def test_no_signal(self):
        e, r = run_cal(400, gain=0.0)
        self.assertEqual(r["status"], lc.STATUS_NONE)
        self.assertIsNone(r["rtt_ms"])
        self.assertIsNone(e.calibration)
        self.assertEqual(e.record_latency_samples, 0)

    def test_clipping(self):
        e, r = run_cal(400, gain=8.0)
        self.assertEqual(r["status"], lc.STATUS_CLIP)
        self.assertIsNone(e.calibration)

    def test_too_quiet(self):
        e, r = run_cal(400, gain=0.004)
        self.assertEqual(r["status"], lc.STATUS_QUIET)
        self.assertIsNone(e.calibration)

    def test_noisy_input_still_ok(self):
        e, r = run_cal(400, noise=0.003)
        self.assertEqual(r["status"], lc.STATUS_OK)
        self.assertLessEqual(abs(r["rtt_samples"] - 400), 1)

    def test_needs_mounted_engine(self):
        with self.assertRaises(RuntimeError):
            make_engine().run_calibration()

    def test_refuses_while_recording(self):
        from track import Track
        e = make_engine()
        e.is_active, e.stream = True, FakeStreamObj()
        t = Track("t", 48000)
        t.recording = True
        e.add_track(t)
        with self.assertRaises(RuntimeError):
            e.run_calibration()


class StatusLineTests(unittest.TestCase):
    def test_not_measured_is_labelled(self):
        e = make_engine()
        e.stream = FakeStreamObj()
        self.assertIn("reported, not measured", rtt_text(e))

    def test_calibration_for_other_mode_is_ignored(self):
        e = make_engine()
        e.active_config = StreamConfig(sample_rate=48000, block_size=64)
        e.set_calibration(10.0, key="WASAPI EXCL 48000/128")
        self.assertIsNone(e.measured_rtt_ms())
        e.set_calibration(10.0)
        self.assertEqual(e.measured_rtt_ms(), 10.0)
        self.assertIn("RTT 10.0 ms (measured)", format_status(e))
        self.assertNotIn("RTT", format_status(e, with_rtt=False))


class SettingsTests(unittest.TestCase):
    def test_calibration_roundtrip_and_validation(self):
        good = {"calibration": {"rtt_ms": 15.2, "key": "WASAPI EXCL 48000/64"}}
        self.assertEqual(ss.sanitize(good)["calibration"], good["calibration"])
        for bad in (None, 5, {"rtt_ms": "x", "key": "k"}, {"rtt_ms": -1, "key": "k"},
                    {"rtt_ms": 10, "key": ""}, {"rtt_ms": True, "key": "k"}, {"rtt_ms": 9999, "key": "k"}):
            self.assertIsNone(ss.sanitize({"calibration": bad})["calibration"])
        self.assertIsNone(ss.DEFAULT_SETTINGS["calibration"])


class CoreTests(unittest.TestCase):
    def test_cli_and_gui_share_one_copy(self):
        import latency_lab
        self.assertIs(latency_lab.analyze, lc.analyze)
        self.assertIs(latency_lab.build_signal, lc.build_signal)

    def test_summarize_pure_delay(self):
        sig, starts, chirp, total = lc.build_signal(48000, 6)
        rec = np.concatenate([np.zeros(200, np.float32), sig * 0.3])[:total]
        r = lc.summarize(rec, 48000, starts, chirp)
        self.assertEqual(r["status"], lc.STATUS_OK)
        self.assertLessEqual(abs(r["rtt_samples"] - 200), 1)


if __name__ == "__main__":
    unittest.main()
