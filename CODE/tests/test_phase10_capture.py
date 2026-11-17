"""Phase 10 / T020: the raw capture tap (capture_recorder.py + engine hooks)."""
import gzip
import csv
import io
import json
import os
import shutil
import tempfile
import time
import tracemalloc
import unittest

import numpy as np
import soundfile as sf

from tests.fake_stream import make_engine, sine
from capture_recorder import CaptureRecorder, BLOCK_COLUMNS

SR = 48000
BLOCK = 64


class TimeInfo:
    def __init__(self, adc, cur, dac):
        self.inputBufferAdcTime = adc
        self.currentTime = cur
        self.outputBufferDacTime = dac


class Status:
    """Truthy like sounddevice.CallbackFlags when any flag is set."""
    def __init__(self, iu=False, io=False, ou=False, oo=False):
        self.input_underflow = iu
        self.input_overflow = io
        self.output_underflow = ou
        self.output_overflow = oo

    def __bool__(self):
        return (self.input_underflow or self.input_overflow
                or self.output_underflow or self.output_overflow)


def drive(engine, signal, block=BLOCK, status_for=None, adc_jitter=None, channels=1):
    """Feed `signal` (frames,) or (frames, ch) through engine._callback with
    time_info and status objects. Returns the list of status objects used."""
    sig = np.asarray(signal, dtype=np.float32)
    if sig.ndim == 1:
        sig = sig.reshape(-1, 1)
    nblocks = len(sig) // block
    used = []
    for b in range(nblocks):
        indata = sig[b * block:(b + 1) * block].copy()
        outdata = np.zeros((block, 2), dtype=np.float32)
        adc = 100.0 + b * block / float(SR)
        if adc_jitter and b in adc_jitter:
            adc += adc_jitter[b]
        ti = TimeInfo(adc, adc + 0.001, adc + 0.01)
        st = status_for(b) if status_for else None
        used.append(st)
        engine._callback(indata, outdata, block, ti, st)
    return used


class TestCaptureExact(unittest.TestCase):
    def test_raw_input_is_bit_exact_with_clean_input_and_effects_on(self):
        """(1) the tap sees the sound card samples, not the cleaned ones."""
        e = make_engine(SR, BLOCK)
        e.input_cleanup_enabled = True              # DC blocker + expander ON
        e.master_fx_l.eq.enabled = True
        e.master_fx_r.eq.enabled = True
        e.input_monitor_enabled = True
        n = 2 * SR
        sig = sine(n, SR, amp=0.3) + np.float32(0.05)   # DC offset: cleanup would change it
        sig = sig.astype(np.float32)
        rec = e.start_capture(max_seconds=3)
        drive(e, sig)
        e.stop_capture()
        got = rec.captured_input()[:, 0]
        self.assertEqual(len(got), (n // BLOCK) * BLOCK)
        self.assertTrue(np.array_equal(got, sig[:len(got)]))
        self.assertFalse(rec.full)

    def test_no_capture_means_same_output_as_before(self):
        a = make_engine(SR, BLOCK)
        b = make_engine(SR, BLOCK)
        sig = sine(SR, SR, amp=0.4)
        outs = []
        for e, cap in ((a, False), (b, True)):
            e.input_monitor_enabled = True
            if cap:
                e.start_capture(max_seconds=2)
            o = []
            for k in range(len(sig) // BLOCK):
                ind = sig[k * BLOCK:(k + 1) * BLOCK].reshape(-1, 1).copy()
                out = np.zeros((BLOCK, 2), dtype=np.float32)
                e._callback(ind, out, BLOCK, None, None)
                o.append(out)
            outs.append(np.concatenate(o))
        self.assertTrue(np.array_equal(outs[0], outs[1]))
        self.assertIsNone(a.capture)

    def test_indata_is_not_modified_by_the_engine(self):
        e = make_engine(SR, BLOCK)
        e.input_cleanup_enabled = True
        ind = (sine(BLOCK, SR) + np.float32(0.1)).reshape(-1, 1).astype(np.float32)
        before = ind.copy()
        e._callback(ind, np.zeros((BLOCK, 2), np.float32), BLOCK, None, None)
        self.assertTrue(np.array_equal(ind, before))


class TestBlockTable(unittest.TestCase):
    def test_one_row_per_callback_with_flags(self):
        """(2) index increases, duration > 0, status bits from the fake status."""
        e = make_engine(SR, BLOCK)
        rec = e.start_capture(max_seconds=2)

        def status_for(b):
            if b == 10:
                return Status(iu=True)
            if b == 20:
                return Status(oo=True, ou=True)
            if b == 30:
                return Status(io=True)
            return None

        drive(e, sine(SR, SR), status_for=status_for)
        e.stop_capture()
        n = SR // BLOCK
        t = rec.blocks_table()
        self.assertEqual(rec.n_blocks, n)
        for k in BLOCK_COLUMNS:
            self.assertEqual(len(t[k]), n)
        self.assertTrue(np.array_equal(t["index"], np.arange(n)))
        self.assertTrue(np.all(np.diff(t["index"]) == 1))
        self.assertTrue(np.all(t["cb_ms"] > 0))
        self.assertTrue(np.all(t["frames"] == BLOCK))
        self.assertTrue(np.array_equal(t["start"], np.arange(n) * BLOCK))
        self.assertEqual(int(t["status"][10]), 1)
        self.assertEqual(int(t["status"][20]), 12)
        self.assertEqual(int(t["status"][30]), 2)
        self.assertEqual(int(np.count_nonzero(t["status"])), 3)

    def test_adc_time_error_is_stored_per_block(self):
        """(3) error = ADC step - frames / rate, in ms; first block nan."""
        e = make_engine(SR, BLOCK)
        rec = e.start_capture(max_seconds=2)
        drive(e, sine(SR // 2, SR), adc_jitter={5: 0.002})   # block 5 arrives 2 ms late
        e.stop_capture()
        t = rec.blocks_table()
        err = t["adc_err_ms"]
        self.assertTrue(np.isnan(err[0]))
        self.assertAlmostEqual(float(err[1]), 0.0, places=3)
        self.assertAlmostEqual(float(err[5]), 2.0, places=2)    # step into block 5 is 2 ms too long
        self.assertAlmostEqual(float(err[6]), -2.0, places=2)   # and 2 ms too short out of it
        self.assertAlmostEqual(float(t["adc_time"][3]), 100.0 + 3 * BLOCK / float(SR), places=6)
        self.assertGreater(float(t["output_time"][3]), float(t["current_time"][3]))

    def test_missing_time_info_gives_nan_not_an_error(self):
        e = make_engine(SR, BLOCK)
        rec = e.start_capture(max_seconds=1)
        for _ in range(5):
            e._callback(np.zeros((BLOCK, 1), np.float32), np.zeros((BLOCK, 2), np.float32),
                        BLOCK, None, None)
        e.stop_capture()
        t = rec.blocks_table()
        self.assertEqual(rec.n_blocks, 5)
        self.assertTrue(np.all(np.isnan(t["adc_time"])))
        self.assertTrue(np.all(np.isnan(t["adc_err_ms"])))


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cap_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_to_files(self):
        """(4) raw.wav, blocks.csv.gz, meta.json."""
        e = make_engine(SR, BLOCK)
        e.input_cleanup_enabled = True
        sig = sine(SR, SR, amp=0.25)
        rec = e.start_capture(max_seconds=2)
        drive(e, sig)
        e.stop_capture()
        folder = os.path.join(self.dir, "cap1")
        paths = rec.to_files(folder, extra_meta={"mode": "TEST 48000/64"})
        self.assertEqual(sorted(os.listdir(folder)), ["blocks.csv.gz", "meta.json", "raw.wav"])
        data, sr = sf.read(paths["raw"], dtype="float32")
        self.assertEqual(sr, SR)
        n = (len(sig) // BLOCK) * BLOCK
        self.assertTrue(np.array_equal(data, sig[:n]))
        with gzip.open(paths["blocks"], "rt", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), n // BLOCK)
        for col in ("start", "frames", "cb_ms", "status", "adc_time"):
            self.assertIn(col, rows[0])
        self.assertEqual(int(rows[3]["start"]), 3 * BLOCK)
        self.assertEqual(int(rows[3]["frames"]), BLOCK)
        self.assertGreater(float(rows[3]["cb_ms"]), 0.0)
        with open(paths["meta"], encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual(meta["sample_rate"], SR)
        self.assertEqual(meta["block_size"], BLOCK)
        self.assertEqual(meta["frames"], n)
        self.assertEqual(meta["blocks"], n // BLOCK)
        self.assertEqual(meta["mode"], "TEST 48000/64")
        self.assertFalse(meta["full"])

    def test_output_file_only_when_requested(self):
        e = make_engine(SR, BLOCK)
        e.input_monitor_enabled = True
        rec = e.start_capture(max_seconds=1, capture_output=True)
        sig = sine(SR // 4, SR, amp=0.2)
        out_l, out_r = [], []
        for k in range(len(sig) // BLOCK):
            ind = sig[k * BLOCK:(k + 1) * BLOCK].reshape(-1, 1).copy()
            out = np.zeros((BLOCK, 2), np.float32)
            e._callback(ind, out, BLOCK, None, None)
            out_l.append(out[:, 0].copy())
        e.stop_capture()
        paths = rec.to_files(os.path.join(self.dir, "c2"))
        data, _ = sf.read(paths["output"], dtype="float32")
        self.assertEqual(data.shape[1], 2)
        self.assertTrue(np.array_equal(data[:, 0], np.concatenate(out_l)))

    def test_multichannel_input_is_kept(self):
        rec = CaptureRecorder(SR, BLOCK, channels_in=2, channels_out=2, max_seconds=1)
        a = sine(BLOCK * 4, SR)
        b = sine(BLOCK * 4, SR, freq=880.0)
        sig = np.stack([a, b], axis=1)
        for k in range(4):
            rec.feed(sig[k * BLOCK:(k + 1) * BLOCK], None, BLOCK, None, None, 0.0, 0.0001)
        paths = rec.to_files(os.path.join(self.dir, "c3"))
        data, _ = sf.read(paths["raw"], dtype="float32")
        self.assertTrue(np.array_equal(data, sig))


class TestRealTimeSafety(unittest.TestCase):
    def test_no_allocation_and_fast_feed(self):
        """(5) < 4 KB allocated over 1000 feeds, < 0.05 ms per feed."""
        rec = CaptureRecorder(SR, BLOCK, 1, 2, max_seconds=60)
        ind = np.ones((BLOCK, 1), dtype=np.float32) * 0.1
        out = np.zeros((BLOCK, 2), dtype=np.float32)
        ti = TimeInfo(1.0, 1.001, 1.01)
        st = Status(iu=True)
        for _ in range(50):                        # warm up
            rec.feed(ind, out, BLOCK, ti, None, 0.0, 0.0002)
        tracemalloc.start()
        base, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        for i in range(1000):
            rec.feed(ind, out, BLOCK, ti, st if i % 100 == 0 else None, 0.0, 0.0002)
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(cur - base, 4096)
        self.assertLess(peak - base, 4096)
        t0 = time.perf_counter()
        for i in range(1000):
            rec.feed(ind, out, BLOCK, ti, None, 0.0, 0.0002)
        avg_ms = (time.perf_counter() - t0) / 1000.0 * 1000.0
        self.assertLess(avg_ms, 0.05)
        self.assertEqual(rec.n_blocks, 2050)

    def test_buffer_full_stops_and_never_grows(self):
        """(7) a full buffer sets `full`, stops, and keeps its size."""
        rec = CaptureRecorder(SR, BLOCK, 1, 2, max_seconds=0.1)   # 4800 frames = 75 blocks
        shapes = (rec.raw.shape, rec.b_start.shape)
        ind = np.full((BLOCK, 1), 0.5, dtype=np.float32)
        for _ in range(200):
            rec.feed(ind, None, BLOCK, None, None, 0.0, 0.0001)
        self.assertTrue(rec.full)
        self.assertFalse(rec.active)
        self.assertEqual(rec.n_blocks, 75)
        self.assertEqual(rec.n_frames, 4800)
        self.assertEqual((rec.raw.shape, rec.b_start.shape), shapes)
        rec.feed(ind, None, BLOCK, None, None, 0.0, 0.0001)      # ignored
        self.assertEqual(rec.n_blocks, 75)

    def test_partial_block_that_does_not_fit_is_dropped_whole(self):
        rec = CaptureRecorder(SR, BLOCK, 1, 2, max_seconds=(BLOCK * 2 + 10) / float(SR))
        ind = np.ones((BLOCK, 1), dtype=np.float32)
        for _ in range(5):
            rec.feed(ind, None, BLOCK, None, None, 0.0, 0.0001)
        self.assertEqual(rec.n_blocks, 2)
        self.assertTrue(rec.full)

    def test_engine_full_flag_in_meta(self):
        e = make_engine(SR, BLOCK)
        rec = e.start_capture(max_seconds=0.05)
        drive(e, sine(SR // 2, SR))
        e.stop_capture()
        d = tempfile.mkdtemp(prefix="cap_")
        try:
            rec.to_files(d)
            with open(os.path.join(d, "meta.json"), encoding="utf-8") as fh:
                self.assertTrue(json.load(fh)["full"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestOtherBranches(unittest.TestCase):
    def test_capture_in_f12_test_signal_branch(self):
        """(6a) the tap still records the raw input while a test tone plays."""
        e = make_engine(SR, BLOCK)
        e.set_test_signal("sine", 0.1)
        sig = sine(SR // 2, SR, amp=0.2)
        rec = e.start_capture(max_seconds=2)
        drive(e, sig)
        e.stop_capture()
        n = (len(sig) // BLOCK) * BLOCK
        self.assertTrue(np.array_equal(rec.captured_input()[:, 0], sig[:n]))
        self.assertEqual(rec.n_blocks, n // BLOCK)
        self.assertEqual(e.telemetry.blocks, n // BLOCK)      # telemetry still counted

    def test_capture_in_calibration_branch(self):
        """(6b) the tap records while the calibration chirps run."""
        class FakeCal:
            calls = 0

            def process(self, indata, outdata, frames):
                FakeCal.calls += 1
                outdata[:] = 0.25

        e = make_engine(SR, BLOCK)
        e._calib = FakeCal()
        sig = sine(SR // 4, SR, amp=0.3)
        rec = e.start_capture(max_seconds=1)
        drive(e, sig)
        e.stop_capture()
        e._calib = None
        n = (len(sig) // BLOCK) * BLOCK
        self.assertEqual(FakeCal.calls, n // BLOCK)
        self.assertTrue(np.array_equal(rec.captured_input()[:, 0], sig[:n]))
        self.assertEqual(rec.n_blocks, n // BLOCK)

    def test_stop_capture_detaches_and_is_safe_twice(self):
        e = make_engine(SR, BLOCK)
        self.assertIsNone(e.stop_capture())
        rec = e.start_capture(max_seconds=1)
        drive(e, sine(SR // 10, SR))
        got = e.stop_capture()
        self.assertIs(got, rec)
        self.assertIsNone(e.capture)
        nb = rec.n_blocks
        drive(e, sine(SR // 10, SR))                 # engine keeps running, tap is off
        self.assertEqual(rec.n_blocks, nb)
        self.assertIsNone(e.stop_capture())

    def test_recorded_tracks_unchanged_by_capture(self):
        """Recorded tracks still hold the CLEANED input, capture or not."""
        from track import Track
        results = []
        for cap in (False, True):
            e = make_engine(SR, BLOCK)
            e.input_cleanup_enabled = True
            t = Track("t", SR)
            e.add_track(t)
            e.arm_track(t, True)
            if cap:
                e.start_capture(max_seconds=2)
            e.start_recording_armed()
            drive(e, sine(SR // 2, SR, amp=0.3) + np.float32(0.05))
            e.stop_recording_armed()
            results.append(np.array(t.buffer[:t.length], copy=True))
        self.assertTrue(np.array_equal(results[0], results[1]))


if __name__ == "__main__":
    unittest.main()
