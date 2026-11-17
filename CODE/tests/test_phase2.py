"""Phase 2 tests: lock-free callback, pre-allocated recording,
latency compensation, effect tails."""
import os
import tempfile
import threading
import time
import unittest
import numpy as np

from tests.fake_stream import make_engine, run_blocks, sine
from track import Track
import project_io

SR = 48000
BLK = 64


def click_train(n, positions, amp=0.8):
    x = np.zeros(n, dtype=np.float32)
    for p in positions:
        x[p] = amp
    return x


class NoLockInCallback(unittest.TestCase):
    def test_callback_runs_while_ui_holds_the_lock(self):
        """If the callback needed engine.lock it would stall for 0.5 s."""
        e = make_engine(SR, BLK)
        t = Track("a", SR)
        t.load_from_array(sine(SR), 0)
        e.add_track(t)
        e.play()
        held = threading.Event()
        release = threading.Event()

        def hog():
            with e.lock:
                held.set()
                release.wait(2.0)

        th = threading.Thread(target=hog)
        th.start()
        held.wait(1.0)
        t0 = time.perf_counter()
        run_blocks(e, sine(BLK * 50))
        elapsed = time.perf_counter() - t0
        release.set()
        th.join()
        self.assertLess(elapsed, 0.4)

    def test_ui_calls_during_10000_blocks(self):
        e = make_engine(SR, BLK)
        base = Track("base", SR)
        base.load_from_array(sine(SR), 0)
        e.add_track(base)
        e.play()
        errors = []
        stop = threading.Event()
        tmp = tempfile.mkdtemp()

        def ui():
            try:
                i = 0
                while not stop.is_set():
                    t = Track(f"t{i}", SR)
                    t.load_from_array(sine(2000), 0)
                    e.add_track(t)
                    e.arm_track(t, True)
                    e.arm_track(t, False)
                    project_io.save_project(os.path.join(tmp, "p.zip"), e)
                    e.remove_track(t)
                    i += 1
            except Exception as ex:      # pragma: no cover
                errors.append(ex)

        th = threading.Thread(target=ui)
        th.start()
        worst = 0.0
        try:
            for _ in range(10000):
                indata = np.zeros((BLK, 1), dtype=np.float32)
                outdata = np.zeros((BLK, 2), dtype=np.float32)
                t0 = time.perf_counter()
                e._callback(indata, outdata, BLK, None, None)
                worst = max(worst, time.perf_counter() - t0)
        finally:
            stop.set()
            th.join()
        self.assertEqual(errors, [])
        # generous: a wait for a save would be tens of ms or more
        self.assertLess(worst, 0.05)


class RecordingBuffer(unittest.TestCase):
    def test_recording_is_preallocated_and_exact(self):
        e = make_engine(SR, BLK)
        t = Track("r", SR)
        e.add_track(t)
        e.arm_track(t, True)
        e.start_recording_armed()
        self.assertGreaterEqual(len(t._rec_buf), SR * 60)   # allocated at start
        buf_id = id(t._rec_buf)
        x = sine(BLK * 100)
        run_blocks(e, x)
        self.assertEqual(id(t._rec_buf), buf_id)            # no re-allocation
        e.stop_recording_armed()
        np.testing.assert_allclose(t.buffer, x, atol=1e-7)

    def test_growth_by_ui_housekeeping(self):
        Track.REC_INITIAL_SECONDS = 0.01        # tiny: 480 samples
        try:
            e = make_engine(SR, BLK)
            t = Track("r", SR)
            e.add_track(t)
            e.arm_track(t, True)
            e.start_recording_armed()
            x = sine(BLK * 40)
            for b in range(40):
                run_blocks(e, x[b * BLK:(b + 1) * BLK])
                e.housekeeping()                 # UI thread would do this
            e.stop_recording_armed()
            np.testing.assert_allclose(t.buffer, x, atol=1e-7)
        finally:
            Track.REC_INITIAL_SECONDS = 300

    def test_emergency_growth_in_callback_loses_nothing(self):
        Track.REC_INITIAL_SECONDS = 0.005
        try:
            e = make_engine(SR, BLK)
            t = Track("r", SR)
            e.add_track(t)
            e.arm_track(t, True)
            e.start_recording_armed()
            x = sine(BLK * 40)
            run_blocks(e, x)                     # no housekeeping at all
            e.stop_recording_armed()
            np.testing.assert_allclose(t.buffer, x, atol=1e-7)
        finally:
            Track.REC_INITIAL_SECONDS = 300


class Compensation(unittest.TestCase):
    def _record_against_loopback(self, delay, comp):
        """A 'sound card' that returns the output `delay` samples late.
        A click is played by track `ref` at timeline position 1024; the
        recorded copy must land on the same timeline position."""
        e = make_engine(SR, BLK)
        e.record_latency_samples = comp
        ref = Track("ref", SR)
        ref.load_from_array(click_train(BLK * 100, [1024]), 0)
        e.add_track(ref)
        rec = Track("rec", SR)
        e.add_track(rec)
        e.arm_track(rec, True)
        e.start_recording_armed()
        n = BLK * 100
        in_sig = np.zeros(n, dtype=np.float32)
        out_l = np.zeros(n, dtype=np.float32)
        for b in range(n // BLK):
            indata = in_sig[b * BLK:(b + 1) * BLK].reshape(-1, 1).copy()
            outdata = np.zeros((BLK, 2), dtype=np.float32)
            e._callback(indata, outdata, BLK, None, None)
            out_l[b * BLK:(b + 1) * BLK] = outdata[:, 0]
            # the loopback: what we played comes back `delay` samples later
            lo = b * BLK + delay
            hi = min(lo + BLK, n)
            if lo < n:
                in_sig[lo:hi] = outdata[:hi - lo, 0]
        e.stop_recording_armed()
        peak_on_timeline = rec.offset + int(np.argmax(np.abs(rec.buffer)))
        return peak_on_timeline

    def test_uncompensated_take_is_late(self):
        late = self._record_against_loopback(delay=400, comp=0)
        self.assertEqual(late, 1024 + 400)

    def test_compensated_take_lines_up_exactly(self):
        pos = self._record_against_loopback(delay=400, comp=400)
        self.assertEqual(pos, 1024)

    def test_compensation_before_time_zero_trims_head(self):
        e = make_engine(SR, BLK)
        e.record_latency_samples = 300
        t = Track("r", SR)
        e.add_track(t)
        e.arm_track(t, True)
        e.start_recording_armed()               # playhead 0 -> offset would be -300
        self.assertEqual(t.offset, 0)
        x = np.arange(BLK * 10, dtype=np.float32) / 1000.0
        run_blocks(e, x)
        e.stop_recording_armed()
        self.assertEqual(t.length, len(x) - 300)
        np.testing.assert_allclose(t.buffer, x[300:], atol=1e-7)

    def test_log_line_written(self):
        lines = []
        e = make_engine(SR, BLK)
        e._log = lambda msg, level="INFO": lines.append(msg)
        e.record_latency_samples = int(0.0082 * SR)
        t = Track("r", SR)
        e.playhead = 10000
        e.add_track(t)
        e.arm_track(t, True)
        e.start_recording_armed()
        self.assertTrue(any("Record offset compensated by 8.2 ms" in l for l in lines))


class Tails(unittest.TestCase):
    def test_delay_tail_continues_after_clip_ends(self):
        e = make_engine(SR, BLK)
        t = Track("d", SR)
        t.load_from_array(click_train(BLK * 4, [0], 0.9), 0)   # short click
        t.effects.delay.enabled = True
        t.effects.delay.time_sec = 0.05
        t.effects.delay.feedback = 0.5
        t.effects.delay.mix = 0.8
        e.add_track(t)
        e.play()
        n = int(0.25 * SR) // BLK * BLK
        out_l, _ = run_blocks(e, np.zeros(n, dtype=np.float32))
        echo_zone = out_l[int(0.04 * SR):int(0.2 * SR)]
        self.assertGreater(float(np.max(np.abs(echo_zone))), 0.01)

    def test_tail_stops_eventually(self):
        e = make_engine(SR, BLK)
        t = Track("d", SR)
        t.load_from_array(click_train(BLK * 2, [0], 0.9), 0)
        t.effects.delay.enabled = True
        t.effects.delay.time_sec = 0.02
        t.effects.delay.feedback = 0.3
        e.add_track(t)
        e.play()
        run_blocks(e, np.zeros(SR * 2, dtype=np.float32))
        self.assertEqual(t.tail_samples_left <= 0, True)


if __name__ == "__main__":
    unittest.main()
