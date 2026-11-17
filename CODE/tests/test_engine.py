"""Phase 0 baseline tests for the transport / mixer (v1.1 behaviour)."""
import unittest
import numpy as np

from tests.fake_stream import make_engine, run_blocks, sine
from track import Track

SR = 48000
BLK = 64


def loaded_track(engine, data, name="T"):
    t = Track(name, engine.sample_rate)
    t.load_from_array(data, 0)
    engine.add_track(t)
    return t


class RecordingTests(unittest.TestCase):
    def test_record_one_second_matches_input(self):
        e = make_engine(SR, BLK)
        t = Track("rec", SR)
        e.add_track(t)
        e.arm_track(t, True)
        e.start_recording_armed()
        x = sine(SR)                      # exactly 1 s
        run_blocks(e, x)
        e.stop_recording_armed()
        self.assertEqual(t.length, (SR // BLK) * BLK)
        np.testing.assert_allclose(t.buffer, x[:t.length], atol=1e-7)
        self.assertFalse(t.recording)

    def test_record_starts_transport_and_anchors_offset(self):
        e = make_engine(SR, BLK)
        e.playhead = 1000
        t = Track("rec", SR)
        e.add_track(t)
        e.arm_track(t, True)
        e.start_recording_armed()
        self.assertTrue(e.is_playing)
        self.assertEqual(t.offset, 1000)

    def test_arming_other_track_commits_take(self):
        e = make_engine(SR, BLK)
        a, b = Track("a", SR), Track("b", SR)
        e.add_track(a)
        e.add_track(b)
        e.arm_track(a, True)
        e.start_recording_armed()
        run_blocks(e, sine(BLK * 10))
        e.arm_track(b, True)              # must NOT discard a's take
        self.assertFalse(a.recording)
        self.assertEqual(a.length, BLK * 10)

    def test_outline_loopback_blends_existing_playback(self):
        e = make_engine(SR, BLK)
        base = loaded_track(e, np.full(BLK * 10, 0.2, dtype=np.float32), "base")
        newt = Track("new", SR)
        e.add_track(newt)
        e.record_with_output_enabled = True
        e.arm_track(newt, True)
        e.start_recording_armed()
        run_blocks(e, np.zeros(BLK * 10, dtype=np.float32))
        e.stop_recording_armed()
        # input was silent, so what got captured is the existing playback
        self.assertGreater(float(np.max(np.abs(newt.buffer))), 0.15)
        self.assertIsNotNone(base)


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.e = make_engine(SR, BLK)
        self.data = (0.2 * np.ones(BLK * 20)).astype(np.float32)

    def test_gain_and_center_pan(self):
        t = loaded_track(self.e, self.data)
        t.gain = 0.5
        self.e.play()
        l, r = run_blocks(self.e, np.zeros(BLK * 20, dtype=np.float32))
        want = 0.2 * 0.5               # rc10: transparent below the limiter knee
        np.testing.assert_allclose(l[BLK:], want, atol=1e-5)
        np.testing.assert_allclose(r[BLK:], want, atol=1e-5)

    def test_hard_pan_right_silences_left(self):
        t = loaded_track(self.e, self.data)
        t.pan = 1.0
        self.e.play()
        l, r = run_blocks(self.e, np.zeros(BLK * 20, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(l))), 1e-6)
        self.assertGreater(float(np.max(np.abs(r))), 0.1)

    def test_mute(self):
        t = loaded_track(self.e, self.data)
        t.mute = True
        self.e.play()
        l, r = run_blocks(self.e, np.zeros(BLK * 20, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(l))), 1e-6)

    def test_solo_silences_other_tracks(self):
        a = loaded_track(self.e, self.data, "a")
        b = loaded_track(self.e, (0.4 * np.ones(BLK * 20)).astype(np.float32), "b")
        b.solo = True
        self.e.play()
        l, _ = run_blocks(self.e, np.zeros(BLK * 20, dtype=np.float32))
        np.testing.assert_allclose(l[BLK:], 0.4, atol=1e-5)    # rc10: no tanh bend
        self.assertIsNotNone(a)

    def test_stopped_transport_does_not_advance(self):
        loaded_track(self.e, self.data)
        run_blocks(self.e, np.zeros(BLK * 5, dtype=np.float32))
        self.assertEqual(self.e.playhead, 0)

    def test_playhead_advances_when_playing(self):
        loaded_track(self.e, self.data)
        self.e.play()
        run_blocks(self.e, np.zeros(BLK * 5, dtype=np.float32))
        self.assertEqual(self.e.playhead, BLK * 5)

    def test_input_monitor_passes_live_input(self):
        self.e.input_monitor_enabled = True
        x = sine(BLK * 4, amp=0.2)
        l, r = run_blocks(self.e, x)
        np.testing.assert_allclose(l, x, atol=1e-5)            # rc10: limiter is transparent here
        np.testing.assert_allclose(r, x, atol=1e-5)

    def test_no_nan_with_silence(self):
        l, r = run_blocks(self.e, np.zeros(BLK * 10, dtype=np.float32))
        self.assertTrue(np.all(np.isfinite(l)) and np.all(np.isfinite(r)))


class LoopTests(unittest.TestCase):
    def test_engine_loop_region_wraps_playhead(self):
        e = make_engine(SR, BLK)
        loaded_track(e, np.ones(BLK * 10, dtype=np.float32) * 0.1)
        e.set_loop_enabled(True)
        self.assertEqual(e.loop_end, BLK * 10)
        e.play()
        run_blocks(e, np.zeros(BLK * 25, dtype=np.float32))
        self.assertEqual(e.playhead, (BLK * 25) % (BLK * 10))

    def test_track_loop_repeats_clip(self):
        e = make_engine(SR, BLK)
        data = np.arange(100, dtype=np.float32) / 1000.0
        t = loaded_track(e, data)
        t.loop_enabled = True
        got = t.get_samples(250, 10)
        want = data[(250 + np.arange(10)) % 100]
        np.testing.assert_allclose(got, want)

    def test_track_without_loop_is_silent_after_end(self):
        t = Track("x", SR)
        t.load_from_array(np.ones(50, dtype=np.float32), 0)
        out = t.get_samples(40, 30)
        self.assertEqual(float(out[:10].sum()), 10.0)
        self.assertEqual(float(out[10:].sum()), 0.0)

    def test_track_offset_places_clip_on_timeline(self):
        t = Track("x", SR)
        t.load_from_array(np.ones(50, dtype=np.float32), 100)
        out = t.get_samples(90, 30)
        self.assertEqual(float(out[:10].sum()), 0.0)
        self.assertEqual(float(out[10:30].sum()), 20.0)


class TransportTests(unittest.TestCase):
    def test_clear_all_tracks_resets_transport(self):
        e = make_engine()
        loaded_track(e, np.ones(100, dtype=np.float32))
        e.playhead = 50
        e.play()
        e.clear_all_tracks()
        self.assertEqual((len(e.tracks), e.playhead, e.is_playing), (0, 0, False))

    def test_arrangement_length_is_longest_track_end(self):
        e = make_engine()
        t = Track("a", SR)
        t.load_from_array(np.ones(100, dtype=np.float32), 30)
        e.add_track(t)
        self.assertEqual(e.arrangement_length(), 130)

    def test_peaks_are_reported(self):
        e = make_engine(SR, BLK)
        e.input_monitor_enabled = True
        run_blocks(e, sine(BLK * 4, amp=0.5))
        self.assertGreater(e.input_peak, 0.4)
        self.assertGreater(e.peak_l, 0.3)


if __name__ == "__main__":
    unittest.main()
