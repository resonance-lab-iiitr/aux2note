"""Phase 0 baseline tests for effects.py. These pin the CURRENT behaviour so
Phase 3 (vectorizing the loops) can prove it changed nothing audible."""
import unittest
import numpy as np

from tests import _stubs  # noqa: F401
from effects import EffectsChain, Delay, Reverb, Compressor, Distortion, Equalizer

SR = 48000


def noise(n, seed=1, amp=0.3):
    return (amp * np.random.RandomState(seed).randn(n)).astype(np.float32)


def run_in_blocks(fx, x, block):
    out = []
    for i in range(0, len(x) - block + 1, block):
        out.append(fx.process(x[i:i + block].copy()))
    return np.concatenate(out)


class PassthroughTests(unittest.TestCase):
    def test_default_chain_is_transparent(self):
        c = EffectsChain(SR)
        x = noise(4096)
        np.testing.assert_allclose(c.process(x.copy()), x, atol=1e-6)

    def test_disabled_effects_return_input(self):
        x = noise(512)
        for fx in (Delay(SR), Reverb(SR), Compressor(SR), Distortion()):
            self.assertFalse(fx.enabled)
            np.testing.assert_array_equal(fx.process(x), x)


class EqTests(unittest.TestCase):
    def test_peak_boost_raises_level_at_center_freq(self):
        eq = Equalizer(SR)
        eq.bands[2].set_gain(12.0)       # 1 kHz band
        t = np.arange(SR) / SR
        x = (0.1 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        y = eq.process(x)
        self.assertGreater(np.sqrt(np.mean(y[SR // 2:] ** 2)),
                           2.5 * np.sqrt(np.mean(x[SR // 2:] ** 2)))


class DelayTests(unittest.TestCase):
    def test_echo_appears_at_delay_time(self):
        d = Delay(SR, time_sec=0.1, feedback=0.0, mix=0.5)
        d.enabled = True
        x = np.zeros(SR, dtype=np.float32)
        x[0] = 1.0
        y = run_in_blocks(d, x, 64)
        # 0.1 s = 4800 samples; block grid is 64 so 4800 is a multiple of 64
        self.assertAlmostEqual(float(y[4800]), 0.5, places=5)
        self.assertAlmostEqual(float(y[0]), 1.0, places=5)

    def test_block_size_independent(self):
        d1, d2 = Delay(SR), Delay(SR)
        d1.enabled = d2.enabled = True
        x = noise(SR)
        a = run_in_blocks(d1, x, 64)
        b = run_in_blocks(d2, x[:len(a)], 512)
        np.testing.assert_allclose(a[:len(b)], b, atol=1e-6)


class ReverbTests(unittest.TestCase):
    def test_has_tail_and_is_finite(self):
        r = Reverb(SR)
        r.enabled = True
        x = np.zeros(SR, dtype=np.float32)
        x[:64] = 0.5
        y = run_in_blocks(r, x, 64)
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertGreater(float(np.max(np.abs(y[4000:20000]))), 1e-4)

    def test_block_size_independent(self):
        r1, r2 = Reverb(SR), Reverb(SR)
        r1.enabled = r2.enabled = True
        x = noise(SR // 2)
        a = run_in_blocks(r1, x, 64)
        b = run_in_blocks(r2, x[:len(a)], 256)
        np.testing.assert_allclose(a[:len(b)], b, atol=1e-5)


class CompressorTests(unittest.TestCase):
    def test_reduces_loud_signal(self):
        c = Compressor(SR, threshold_db=-20.0, ratio=4.0)
        c.enabled = True
        x = (0.8 * np.ones(SR // 2)).astype(np.float32)
        y = run_in_blocks(c, x, 64)
        self.assertLess(float(np.mean(y[-2000:])), 0.5)

    def test_leaves_quiet_signal_alone(self):
        c = Compressor(SR, threshold_db=-10.0, ratio=4.0)
        c.enabled = True
        x = (0.01 * np.ones(4096)).astype(np.float32)
        y = run_in_blocks(c, x, 64)
        np.testing.assert_allclose(y, x, atol=1e-6)

    def test_block_size_independent(self):
        c1, c2 = Compressor(SR), Compressor(SR)
        c1.enabled = c2.enabled = True
        x = noise(SR // 2, amp=0.6)
        a = run_in_blocks(c1, x, 64)
        b = run_in_blocks(c2, x[:len(a)], 512)
        np.testing.assert_allclose(a[:len(b)], b, atol=1e-5)


class DistortionTests(unittest.TestCase):
    def test_bounded_output(self):
        d = Distortion(drive=1.0, mix=1.0)
        d.enabled = True
        y = d.process(noise(2048, amp=2.0))
        self.assertLessEqual(float(np.max(np.abs(y))), 1.0 + 1e-6)


class ChainSerializationTests(unittest.TestCase):
    def test_to_from_dict_round_trip(self):
        c = EffectsChain(SR)
        c.delay.enabled = True
        c.delay.time_sec = 0.2
        c.reverb.enabled = True
        c.reverb.room_size = 0.9
        c.compressor.ratio = 6.0
        c2 = EffectsChain(SR)
        c2.from_dict(c.to_dict())
        self.assertEqual(c.to_dict(), c2.to_dict())

    def test_clone_has_same_params_but_fresh_state(self):
        c = EffectsChain(SR)
        c.delay.enabled = True
        c.process(noise(1024))
        k = c.clone()
        self.assertEqual(c.to_dict(), k.to_dict())
        self.assertFalse(np.any(k.delay._buf))

    def test_extreme_params_stay_finite(self):
        c = EffectsChain(SR)
        c.compressor.enabled = c.distortion.enabled = True
        c.delay.enabled = c.reverb.enabled = True
        c.delay.feedback = 0.95
        c.reverb.room_size = 1.0
        y = run_in_blocks(c, noise(SR, amp=1.0), 128)
        self.assertTrue(np.all(np.isfinite(y)))


if __name__ == "__main__":
    unittest.main()
