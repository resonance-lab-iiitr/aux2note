"""rc10 "clean audio" tests: DC blocker, noise expander, soft limiter,
anti-aliased distortion, parameter smoothing, tail fades / state reset,
denormal flush, and the stopped-transport silence fix."""
import unittest
import numpy as np

from tests.fake_stream import make_engine, run_blocks, sine
from track import Track
from effects import (
    ParamSmoother, DCBlocker, DownwardExpander, InputCleanup, soft_limit,
    flush_small, Distortion, Delay, Reverb, Compressor, EffectsChain,
)

SR = 48000
BLK = 128


def in_blocks(fx, x, block=BLK):
    return np.concatenate([fx.process(x[i:i + block].copy())
                           for i in range(0, len(x) - block + 1, block)])


def loaded(engine, data, name="T"):
    t = Track(name, engine.sample_rate)
    t.load_from_array(data, 0)
    engine.add_track(t)
    return t


class SoftLimitTests(unittest.TestCase):
    def test_transparent_below_knee(self):
        x = np.linspace(-0.8, 0.8, 1001).astype(np.float32)
        np.testing.assert_array_equal(soft_limit(x), x)

    def test_bounded_and_monotonic_above_knee(self):
        x = np.linspace(0.0, 20.0, 4001).astype(np.float32)
        y = soft_limit(x)
        self.assertLessEqual(float(y.max()), 1.0)
        self.assertTrue(np.all(np.diff(y) >= -1e-7))

    def test_no_corner_at_the_knee(self):
        e = 1e-3
        below = (soft_limit(np.array([0.8], np.float32))[0] - soft_limit(np.array([0.8 - e], np.float32))[0]) / e
        above = (soft_limit(np.array([0.8 + e], np.float32))[0] - soft_limit(np.array([0.8], np.float32))[0]) / e
        self.assertAlmostEqual(float(below), float(above), delta=0.02)

    def test_odd_symmetry(self):
        x = np.linspace(0, 5, 101).astype(np.float32)
        np.testing.assert_allclose(soft_limit(-x), -soft_limit(x), atol=1e-6)


class ParamSmootherTests(unittest.TestCase):
    def test_first_call_snaps(self):
        s = ParamSmoother(SR)
        self.assertEqual(s.step(0.7, 128), 0.7)

    def test_steady_value_is_plain_float(self):
        s = ParamSmoother(SR)
        s.step(0.5, 128)
        self.assertIsInstance(s.step(0.5, 128), float)

    def test_glides_monotonically_and_arrives(self):
        s = ParamSmoother(SR, 10.0)
        s.step(0.0, 128)
        vals = []
        for _ in range(400):
            v = s.step(1.0, 128)
            vals.append(np.atleast_1d(v))
        y = np.concatenate(vals)
        self.assertTrue(np.all(np.diff(y) >= -1e-12))
        self.assertLess(float(y[0]), 0.05)               # starts near the old value
        self.assertAlmostEqual(float(y[-1]), 1.0, places=4)


class DCBlockerTests(unittest.TestCase):
    def test_removes_dc_offset(self):
        x = (0.2 + sine(SR, amp=0.1)).astype(np.float32)
        y = in_blocks(DCBlocker(SR), x)
        self.assertAlmostEqual(float(np.mean(y[SR // 2:])), 0.0, places=3)

    def test_passes_music_band_unchanged(self):
        x = sine(SR, freq=440.0, amp=0.5)
        y = in_blocks(DCBlocker(SR), x)
        rms_in = float(np.sqrt(np.mean(x[SR // 2:len(y)] ** 2)))
        rms_out = float(np.sqrt(np.mean(y[SR // 2:] ** 2)))
        self.assertAlmostEqual(rms_out / rms_in, 1.0, delta=0.01)


class ExpanderTests(unittest.TestCase):
    def test_loud_signal_passes_untouched(self):
        x = sine(SR, amp=0.3)
        y = in_blocks(DownwardExpander(SR), x)
        np.testing.assert_allclose(y, x[:len(y)], atol=1e-6)

    def test_quiet_noise_is_reduced(self):
        rs = np.random.RandomState(1)
        noise = (10 ** (-75 / 20.0) * rs.randn(SR) / 3.0).astype(np.float32)   # ~ -85 dBFS rms
        y = in_blocks(DownwardExpander(SR), noise)
        ratio_db = 20 * np.log10(np.std(y[SR // 2:]) / np.std(noise[SR // 2:len(y)]))
        self.assertLess(float(ratio_db), -10.0)

    def test_gain_never_steps(self):
        """loud note then silence-ish: the gain must glide, not jump."""
        loud = sine(SR // 4, amp=0.3)
        quiet = (0.5 * 10 ** (-80 / 20.0) * sine(SR // 2, amp=1.0)).astype(np.float32)
        x = np.concatenate([loud, quiet])
        ex = DownwardExpander(SR)
        gains = []
        for i in range(0, len(x) - BLK + 1, BLK):
            blk = x[i:i + BLK].copy()
            ex.process(blk)
            gains.append(ex._gain)
        steps = np.abs(np.diff(gains))
        self.assertLess(float(steps.max()), 0.35)         # no block-to-block cliff
        self.assertLess(gains[-1], 0.3)                   # ...but it did close in the end

    def test_input_cleanup_chain_runs(self):
        x = sine(BLK * 8, amp=0.2)
        y = in_blocks(InputCleanup(SR), x)
        self.assertTrue(np.all(np.isfinite(y)))


class DistortionTests(unittest.TestCase):
    @staticmethod
    def alias_db(y, f0):
        w = np.hanning(len(y))
        S = np.abs(np.fft.rfft(y * w)) ** 2
        f = np.fft.rfftfreq(len(y), 1 / SR)
        band = (f > 200) & (f < f0 * 0.85)           # below the fundamental only aliases land here
        fund = np.abs(f - f0) < 60
        return 10 * np.log10(S[band].sum() / S[fund].sum())

    def test_aliasing_is_much_lower_than_plain_tanh(self):
        f0 = 4300.0
        x = sine(SR, freq=f0, amp=0.6)
        a = 6.0                                                    # drive 1.0
        naive = np.tanh(a * x.astype(np.float64)) / np.tanh(a)
        d = Distortion(drive=1.0, mix=1.0, sample_rate=SR)
        d.enabled = True
        y = in_blocks(d, x)
        gain = self.alias_db(naive, f0) - self.alias_db(y, f0)
        self.assertGreater(gain, 20.0)

    def test_block_size_does_not_change_the_sound(self):
        x = sine(BLK * 40, amp=0.5)
        outs = []
        for blk in (64, 128, 512):
            d = Distortion(drive=0.6, mix=0.8, sample_rate=SR)
            d.enabled = True
            outs.append(in_blocks(d, x, blk)[:BLK * 32])
        np.testing.assert_allclose(outs[0], outs[1], atol=1e-6)
        np.testing.assert_allclose(outs[0], outs[2], atol=1e-6)

    def test_quiet_signals_get_at_most_6x(self):
        x = (0.001 * np.sin(2 * np.pi * 220 * np.arange(BLK * 20) / SR)).astype(np.float32)
        d = Distortion(drive=1.0, mix=1.0, sample_rate=SR)
        d.enabled = True
        y = in_blocks(d, x)
        g = float(np.std(y[BLK * 5:]) / np.std(x[BLK * 5:len(y)]))
        self.assertLessEqual(g, 6.2)                    # was up to 10x before rc10
        self.assertGreater(g, 5.0)

    def test_drive_change_has_no_step(self):
        x = sine(BLK * 60, amp=0.3, freq=200.0)
        d = Distortion(drive=0.1, mix=1.0, sample_rate=SR)
        d.enabled = True
        first = in_blocks(d, x[:BLK * 30])
        d.drive = 1.0                                    # slider jumps
        second = in_blocks(d, x[BLK * 30:])
        y = np.concatenate([first, second])
        steady = float(np.max(np.abs(np.diff(first))))
        self.assertLess(float(np.max(np.abs(np.diff(y)))), 2.5 * steady + 0.02)


class SmoothedParameterTests(unittest.TestCase):
    def test_delay_time_change_crossfades(self):
        x = sine(SR, freq=300.0, amp=0.4)
        d = Delay(SR, time_sec=0.010, feedback=0.0, mix=1.0)
        d.enabled = True
        a = in_blocks(d, x[:BLK * 200])
        d.time_sec = 0.0123                              # jump of ~110 samples
        b = in_blocks(d, x[BLK * 200:BLK * 260])
        y = np.concatenate([a, b])
        steady = float(np.max(np.abs(np.diff(a[BLK * 50:]))))
        self.assertLess(float(np.max(np.abs(np.diff(y)))), 2.0 * steady + 0.02)

    def test_compressor_makeup_change_is_gradual(self):
        x = sine(BLK * 120, freq=150.0, amp=0.05)        # below threshold: only makeup acts
        c = Compressor(SR)
        c.enabled = True
        c.makeup_db = 0.0
        first = in_blocks(c, x[:BLK * 60])
        c.makeup_db = 12.0
        second = in_blocks(c, x[BLK * 60:])
        y = np.concatenate([first, second])
        # a 12 dB step would make one sample jump by ~0.15; gliding stays tiny
        self.assertLess(float(np.max(np.abs(np.diff(y)))), 0.05)

    def test_reverb_mix_change_is_gradual(self):
        x = sine(BLK * 120, freq=150.0, amp=0.3)
        r = Reverb(SR, mix=0.0)
        r.enabled = True
        first = in_blocks(r, x[:BLK * 60])
        r.mix = 1.0
        second = in_blocks(r, x[BLK * 60:])
        y = np.concatenate([first, second])
        steady = float(np.max(np.abs(np.diff(first))))
        self.assertLess(float(np.max(np.abs(np.diff(y)))), 3.0 * steady + 0.05)


class TransportTests(unittest.TestCase):
    def test_stopped_transport_is_silent(self):
        """rc10 regression: STOP used to repeat one frozen block (a buzz)."""
        e = make_engine(SR, BLK)
        loaded(e, sine(BLK * 40, amp=0.5))
        l, r = run_blocks(e, np.zeros(BLK * 10, dtype=np.float32))
        self.assertEqual(float(np.max(np.abs(l))), 0.0)
        self.assertEqual(float(np.max(np.abs(r))), 0.0)

    def test_stop_fades_out_then_stays_silent(self):
        e = make_engine(SR, BLK)
        loaded(e, np.full(BLK * 400, 0.4, dtype=np.float32))
        e.play()
        run_blocks(e, np.zeros(BLK * 20, dtype=np.float32))
        e.stop()
        l, _ = run_blocks(e, np.zeros(BLK * 60, dtype=np.float32))
        self.assertGreater(float(l[0]), 0.1)                      # no instant cut
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.02)  # no step
        self.assertEqual(float(np.max(np.abs(l[-BLK * 10:]))), 0.0)  # exactly silent after ~100 ms

    def test_play_fades_in(self):
        e = make_engine(SR, BLK)
        loaded(e, np.full(BLK * 400, 0.4, dtype=np.float32))
        run_blocks(e, np.zeros(BLK * 4, dtype=np.float32))
        e.play()
        l, _ = run_blocks(e, np.zeros(BLK * 30, dtype=np.float32))
        self.assertLess(float(l[0]), 0.05)
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.02)
        self.assertAlmostEqual(float(l[-1]), 0.4, places=3)


class MixerSmoothingTests(unittest.TestCase):
    def setUp(self):
        self.e = make_engine(SR, BLK)
        self.t = loaded(self.e, np.full(BLK * 600, 0.4, dtype=np.float32))
        self.e.play()
        run_blocks(self.e, np.zeros(BLK * 30, dtype=np.float32))     # settle

    def test_master_volume_glides(self):
        self.e.master_gain = 0.0
        l, _ = run_blocks(self.e, np.zeros(BLK * 40, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.01)
        self.assertLess(abs(float(l[-1])), 1e-3)

    def test_track_volume_glides(self):
        self.t.gain = 0.0
        l, _ = run_blocks(self.e, np.zeros(BLK * 40, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.01)

    def test_mute_fades(self):
        self.t.mute = True
        l, _ = run_blocks(self.e, np.zeros(BLK * 40, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.01)
        self.assertLess(abs(float(l[-1])), 1e-3)

    def test_pan_glides(self):
        self.t.pan = 1.0
        l, r = run_blocks(self.e, np.zeros(BLK * 40, dtype=np.float32))
        self.assertLess(float(np.max(np.abs(np.diff(l)))), 0.01)
        self.assertLess(float(np.max(np.abs(np.diff(r)))), 0.01)
        self.assertLess(abs(float(l[-1])), 1e-3)


class TailAndStateTests(unittest.TestCase):
    def _clicky_track(self, e):
        data = np.zeros(BLK * 4, dtype=np.float32)
        data[:BLK] = 0.8
        t = loaded(e, data)
        t.effects.delay.enabled = True
        t.effects.delay.time_sec = 0.02
        t.effects.delay.feedback = 0.4
        t.effects.reverb.enabled = True
        return t

    def test_state_is_cleared_when_the_tail_ends(self):
        e = make_engine(SR, BLK)
        t = self._clicky_track(e)
        e.play()
        run_blocks(e, np.zeros(SR * 6, dtype=np.float32))
        self.assertLessEqual(t.tail_samples_left, 0)
        self.assertFalse(np.any(t.effects.delay._buf))
        for l in t.effects.reverb.combs + t.effects.reverb.allpasses:
            self.assertFalse(np.any(l.buf))

    def test_stop_clears_effect_state(self):
        e = make_engine(SR, BLK)
        t = self._clicky_track(e)
        e.play()
        run_blocks(e, np.zeros(BLK * 3, dtype=np.float32))
        self.assertTrue(np.any(t.effects.delay._buf))
        e.stop()
        run_blocks(e, np.zeros(BLK * 40, dtype=np.float32))
        self.assertFalse(np.any(t.effects.delay._buf))

    def test_chain_reset_state_clears_everything(self):
        c = EffectsChain(SR)
        c.eq.bands[2].set_gain(6.0)
        c.compressor.enabled = c.distortion.enabled = c.delay.enabled = c.reverb.enabled = True
        in_blocks(c, sine(BLK * 20, amp=0.5))
        c.reset_state()
        self.assertFalse(np.any(c.delay._buf))
        self.assertFalse(any(np.any(b.zi) for b in c.eq.bands))
        self.assertEqual(c.distortion._xprev, 0.0)
        self.assertLessEqual(c.compressor._env, 1e-5)
        y = c.process(np.zeros(BLK, dtype=np.float32))
        self.assertEqual(float(np.max(np.abs(y))), 0.0)


class DenormalTests(unittest.TestCase):
    def test_flush_small_zeroes_only_tiny_values(self):
        a = np.array([1e-38, 5e-33, 1e-20, 0.25, -0.5, -1e-35], dtype=np.float32)
        flush_small(a, 1e-30)
        np.testing.assert_array_equal(a, np.array([0, 0, 1e-20, 0.25, -0.5, 0], dtype=np.float32))

    def test_chain_flush_clears_tiny_feedback_values(self):
        c = EffectsChain(SR)
        c.delay.enabled = c.reverb.enabled = True
        c.delay._buf[100:200] = 1e-36
        c.reverb.combs[0].buf[:50] = 1e-37
        for _ in range(EffectsChain.FLUSH_STEPS):         # one full sweep
            c.flush_denormals()
        self.assertFalse(np.any(c.delay._buf))
        self.assertFalse(np.any(c.reverb.combs[0].buf))

    def test_long_silence_never_makes_nonfinite_or_tiny_state(self):
        c = EffectsChain(SR)
        c.eq.bands[2].set_gain(6.0)
        c.compressor.enabled = c.distortion.enabled = c.delay.enabled = c.reverb.enabled = True
        c.delay.feedback = 0.5
        in_blocks(c, sine(BLK * 20, amp=0.5))
        for i in range(2000):                            # ~5 s of silence
            c.process(np.zeros(BLK, dtype=np.float32))
            if i % 16 == 0:
                c.flush_denormals()
        for b in c.eq.bands:
            self.assertTrue(np.all((np.abs(b.zi) >= 1e-30) | (b.zi == 0)))
        self.assertGreaterEqual(c.compressor._env, 1e-12)


class EngineInputCleanupTests(unittest.TestCase):
    def _monitor_engine(self, cleanup):
        e = make_engine(SR, BLK)
        e.input_cleanup_enabled = cleanup
        e.input_monitor_enabled = True
        return e

    def test_dc_offset_is_removed_from_live_monitoring(self):
        x = (0.15 + sine(SR, amp=0.1)).astype(np.float32)
        on, _ = run_blocks(self._monitor_engine(True), x)
        off, _ = run_blocks(self._monitor_engine(False), x)
        self.assertAlmostEqual(float(np.mean(on[SR // 2:])), 0.0, places=3)
        self.assertGreater(float(np.mean(off[SR // 2:])), 0.1)

    def test_background_hiss_is_quieter_with_cleanup(self):
        rs = np.random.RandomState(2)
        hiss = (10 ** (-80 / 20.0) * rs.randn(SR) / 3.0).astype(np.float32)
        on, _ = run_blocks(self._monitor_engine(True), hiss)
        off, _ = run_blocks(self._monitor_engine(False), hiss)
        self.assertLess(float(np.std(on[SR // 2:])), 0.4 * float(np.std(off[SR // 2:])))

    def test_normal_playing_level_is_untouched(self):
        x = sine(SR, amp=0.3, freq=330.0)
        on, _ = run_blocks(self._monitor_engine(True), x)
        r_in = float(np.sqrt(np.mean(x[SR // 2:len(on)] ** 2)))
        r_out = float(np.sqrt(np.mean(on[SR // 2:] ** 2)))
        self.assertAlmostEqual(r_out / r_in, 1.0, delta=0.02)

    def test_input_meter_still_shows_the_raw_input(self):
        e = self._monitor_engine(True)
        x = (0.3 * np.ones(BLK * 4)).astype(np.float32)           # pure DC
        run_blocks(e, x)
        self.assertAlmostEqual(e.input_peak, 0.3, places=3)


if __name__ == "__main__":
    unittest.main()
