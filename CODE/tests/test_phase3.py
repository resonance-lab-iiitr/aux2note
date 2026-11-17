"""Phase 3 tests: vectorized DSP matches the v1.1 per-sample code, is
block-size independent, stays finite with extreme settings, and a UI change
never wipes a reverb tail."""
import unittest
import numpy as np

from tests import _stubs  # noqa: F401
from effects import Delay, Reverb, Compressor, EffectsChain, benchmark_costs
from tests.reference_dsp import DelayReference, ReverbReference, CompressorReference

SR = 48000


def noise(n, seed=3, amp=0.3):
    return (amp * np.random.RandomState(seed).randn(n)).astype(np.float32)


def blocks(fx, x, block):
    return np.concatenate([fx.process(x[i:i + block].copy()) for i in range(0, len(x) - block + 1, block)])


def both(new, ref, **params):
    for fx in (new, ref):
        fx.enabled = True
        for k, v in params.items():
            setattr(fx, k, v)
    return new, ref


class MatchesReference(unittest.TestCase):
    def test_delay_matches_v11(self):
        # includes a delay shorter than the block (chunked path) and one that wraps
        for t, fb, block in [(0.35, 0.4, 64), (0.2, 0.9, 512), (0.003, 0.5, 512), (0.01, 0.3, 64)]:
            with self.subTest(time=t, block=block):
                new, ref = both(Delay(SR), DelayReference(SR), time_sec=t, feedback=fb, mix=0.4)
                x = noise(SR)
                np.testing.assert_allclose(blocks(new, x, block), blocks(ref, x, block), atol=1e-5)

    def test_delay_buffer_wraps(self):
        new, ref = both(Delay(SR, max_seconds=0.5), DelayReference(SR, max_seconds=0.5),
                        time_sec=0.4, feedback=0.6, mix=0.5)
        x = noise(SR * 2)
        np.testing.assert_allclose(blocks(new, x, 100), blocks(ref, x, 100), atol=1e-5)

    def test_reverb_matches_v11(self):
        for room, damp, block in [(0.7, 0.3, 64), (1.0, 0.0, 256), (0.2, 1.0, 64), (0.6, 0.5, 100)]:
            with self.subTest(room=room, damp=damp, block=block):
                new, ref = both(Reverb(SR), ReverbReference(SR), room_size=room, damping=damp, mix=0.35)
                new._build()
                ref._build()
                x = noise(SR // 2)
                np.testing.assert_allclose(blocks(new, x, block), blocks(ref, x, block), atol=1e-4)

    def test_compressor_matches_v11(self):
        for thr, ratio, atk, rel in [(-24, 4, 8, 120), (-30, 10, 1, 50), (-12, 2, 30, 300)]:
            with self.subTest(thr=thr, ratio=ratio):
                new, ref = both(Compressor(SR), CompressorReference(SR), threshold_db=thr,
                                ratio=ratio, attack_ms=atk, release_ms=rel)
                x = noise(SR // 2, amp=0.5)
                x[2000:4000] *= 0.05                       # quiet gap -> release phase
                np.testing.assert_allclose(blocks(new, x, 64), blocks(ref, x, 64), atol=2e-3)


class BlockSizeIndependence(unittest.TestCase):
    def test_one_big_block_equals_many_small(self):
        x = noise(4096, amp=0.5)

        def chain():
            c = EffectsChain(SR)
            c.compressor.enabled = c.delay.enabled = c.reverb.enabled = c.distortion.enabled = True
            c.delay.time_sec = 0.02
            c.eq.bands[2].set_gain(6.0)
            return c

        big = chain().process(x.copy())
        small = blocks(chain(), x, 64)
        np.testing.assert_allclose(big, small, atol=1e-4)

    def test_each_effect_block_independent_odd_sizes(self):
        n = 3000                                   # 50 blocks of 60, 6 blocks of 500
        x = noise(n, amp=0.5)
        for make in (lambda: Delay(SR, time_sec=0.01), lambda: Reverb(SR), lambda: Compressor(SR)):
            a, b = make(), make()
            a.enabled = b.enabled = True
            np.testing.assert_allclose(blocks(a, x, 60), blocks(b, x, 500), atol=1e-4)


class Stability(unittest.TestCase):
    def test_extreme_parameters_stay_finite(self):
        x = noise(SR // 2, amp=10.0)
        c = EffectsChain(SR)
        c.compressor.enabled = c.delay.enabled = c.reverb.enabled = c.distortion.enabled = True
        c.delay.feedback, c.delay.time_sec, c.delay.mix = 5.0, 0.0, 3.0
        c.reverb.room_size, c.reverb.damping, c.reverb.mix = 5.0, -2.0, 3.0
        c.compressor.ratio, c.compressor.threshold_db = 0.0, -200.0
        c.compressor.attack_ms, c.compressor.release_ms = 0.0, 0.0
        for block in (32, 64, 4096):
            y = blocks(c, x, block)
            self.assertTrue(np.all(np.isfinite(y)), f"block {block}")

    def test_silence_stays_silent_and_finite(self):
        c = EffectsChain(SR)
        c.compressor.enabled = c.delay.enabled = c.reverb.enabled = True
        y = blocks(c, np.zeros(8192, dtype=np.float32), 64)
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertEqual(float(np.max(np.abs(y))), 0.0)


class ReverbParameterChanges(unittest.TestCase):
    def test_room_size_change_keeps_the_tail(self):
        r = Reverb(SR)
        r.enabled = True
        x = np.zeros(4096, dtype=np.float32)
        x[:64] = 0.5
        blocks(r, x, 64)
        energy = sum(float(np.sum(np.abs(c.buf))) for c in r.combs)
        self.assertGreater(energy, 0.0)
        r.set_room_size(0.9)
        r.process(np.zeros(64, dtype=np.float32))
        after = sum(float(np.sum(np.abs(c.buf))) for c in r.combs)
        self.assertGreater(after, 0.5 * energy)                       # not wiped
        # rc10: feedback now glides to the new value (~10 ms) instead of jumping
        old_fb = 0.6 + 0.6 * 0.38
        new_fb = 0.6 + 0.9 * 0.38
        self.assertGreater(r.combs[0].feedback, old_fb)
        self.assertLess(r.combs[0].feedback, new_fb)
        for _ in range(200):                                          # ~270 ms later
            r.process(np.zeros(64, dtype=np.float32))
        self.assertAlmostEqual(r.combs[0].feedback, new_fb, places=6)

    def test_ui_changes_never_rebuild_buffers(self):
        r = Reverb(SR)
        r.enabled = True
        bufs = [id(c.buf) for c in r.combs] + [id(a.buf) for a in r.allpasses]
        r.set_room_size(0.2)
        r.from_dict({"enabled": True, "room_size": 0.8, "damping": 0.1, "mix": 0.5})
        r.process(noise(64))
        self.assertEqual(bufs, [id(c.buf) for c in r.combs] + [id(a.buf) for a in r.allpasses])


class Speed(unittest.TestCase):
    def test_benchmark_reports_every_effect(self):
        costs = benchmark_costs(SR, 64, reps=30)
        self.assertEqual(set(costs), {"EQ (5 band)", "Compressor", "Distortion", "Delay", "Reverb", "ALL (chain)"})
        # Real target is < 20% (see tools/dsp_bench.py). Loose bound here so a
        # slow or busy CI machine does not fail the suite.
        self.assertLess(costs["ALL (chain)"], 60.0)


if __name__ == "__main__":
    unittest.main()
