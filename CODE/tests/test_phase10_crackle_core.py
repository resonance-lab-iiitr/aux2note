"""Phase 10 (T018): crackle_core finds clicks, dropouts, clipping, DC, hum and says
what they point to. Every signal is synthetic with injected faults of known
size and position, and each test states its threshold.

Run from CODE/:  python3 -m unittest tests.test_phase10_crackle_core
"""
import os
import tempfile
import unittest

import numpy as np
from scipy import signal as sig

import crackle_core as cc

SR = 48000
BLOCK = 128
NOISE = 1e-4           # "low noise": sigma 1e-4 = -80 dBFS


def sine(dur, f=440.0, a=0.3, noise=NOISE, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * SR)) / SR
    return a * np.sin(2 * np.pi * f * t) + rng.normal(0.0, noise, len(t))


def silence(dur, noise=NOISE, seed=0):
    return np.random.default_rng(seed).normal(0.0, noise, int(dur * SR))


def speech_like(dur, seed=3):
    """Voiced bursts (harmonic series, 4 ms attack, 20 ms release, 300-3500 Hz) with
    pauses, plus low noise."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    pos = 0.2
    while pos < dur - 0.5:
        length = rng.uniform(0.15, 0.5)
        f0 = rng.uniform(100, 220)
        i0, i1 = int(pos * SR), min(int((pos + length) * SR), n)
        tt = t[i0:i1]
        h = sum(np.sin(2 * np.pi * f0 * k * tt + rng.uniform(0, 6)) / k for k in range(1, 25))
        env = np.minimum(1, (tt - tt[0]) / 0.004) * np.minimum(1, (tt[-1] - tt) / 0.02)
        x[i0:i1] += 0.15 * h * env
        pos += length + rng.uniform(0.1, 0.4)
    sos = sig.butter(2, [300, 3500], btype="band", fs=SR, output="sos")
    return sig.sosfilt(sos, x) + rng.normal(0, NOISE, n)


def inject_clicks(x, positions, widths, amps, shape="rect"):
    """Add clicks in place. shape 'rect' = flat pulse, 'bump' = half-sine pulse."""
    for p, w, a in zip(positions, widths, amps):
        if shape == "rect":
            x[p:p + w] += a
        else:
            x[p:p + w] += a * np.sin(np.pi * (np.arange(w) + 0.5) / w)
    return x


def random_clicks(rng, n_samples, count, min_gap=5000):
    pos = np.sort(rng.choice(np.arange(min_gap, n_samples - min_gap, min_gap), count, replace=False))
    widths = rng.integers(1, 9, count)                           # 1 to 8 samples
    amps = rng.uniform(0.05, 0.5, count) * rng.choice([-1, 1], count)   # 0.05 to 0.5
    return pos, widths, amps


def recall(events, positions, tol=12):
    st = np.array([e["start"] for e in events])
    return sum(bool(np.any(np.abs(st - p) <= tol)) for p in positions) / float(len(positions))


def make_blocks(n_samples, block, late_idx=(), status_idx=(), block_ms_cb=0.5):
    nb = n_samples // block
    cb = np.full(nb, block_ms_cb)
    cb[list(late_idx)] = block / SR * 1000.0 * 1.5            # 150 % of the block time
    st = np.zeros(nb, int)
    st[list(status_idx)] = 4
    return {"start": np.arange(nb) * block, "frames": np.full(nb, block),
            "cb_ms": cb, "status": st}


class ClickTests(unittest.TestCase):
    """Threshold (1): recall >= 95 % and <= 1 false event per minute."""

    def test_clean_sine_has_at_most_one_false_event_per_minute(self):
        ev = cc.detect_clicks(sine(60.0), SR)
        self.assertLessEqual(len(ev), 1)

    def test_clean_noise_and_digital_silence_give_no_clicks(self):
        self.assertEqual(cc.detect_clicks(silence(20.0), SR), [])
        self.assertEqual(cc.detect_clicks(np.zeros(SR * 2), SR), [])

    def test_recall_rectangular_clicks_1_to_8_samples(self):
        rng = np.random.default_rng(1)
        x = sine(60.0, seed=1)
        pos, w, a = random_clicks(rng, len(x), 60)
        inject_clicks(x, pos, w, a, "rect")
        ev = cc.detect_clicks(x, SR)
        self.assertGreaterEqual(recall(ev, pos), 0.95)
        self.assertLessEqual(len(ev) - len(pos), 1)              # false events in this minute

    def test_recall_smooth_clicks_1_to_8_samples(self):
        rng = np.random.default_rng(2)
        x = sine(60.0, seed=2)
        pos, w, a = random_clicks(rng, len(x), 60)
        inject_clicks(x, pos, w, a, "bump")
        ev = cc.detect_clicks(x, SR)
        self.assertGreaterEqual(recall(ev, pos), 0.95)
        self.assertLessEqual(len(ev) - len(pos), 1)

    def test_clicks_in_silence(self):
        rng = np.random.default_rng(4)
        x = silence(30.0, seed=4)
        pos, w, a = random_clicks(rng, len(x), 30)
        inject_clicks(x, pos, w, a)
        ev = cc.detect_clicks(x, SR)
        self.assertGreaterEqual(recall(ev, pos), 0.95)
        self.assertLessEqual(len(ev) - len(pos), 1)

    def test_speech_like_bursts_recall_and_false_rate(self):
        """Threshold on speech-like material: recall >= 95 %, <= 2 false events per minute."""
        x = speech_like(60.0)
        false_only = cc.detect_clicks(x, SR)
        self.assertLessEqual(len(false_only), 2)
        rng = np.random.default_rng(5)
        pos = np.sort(rng.choice(np.arange(20000, len(x) - 20000, 20000), 40, replace=False))
        inject_clicks(x, pos, [2] * len(pos), 0.1 * rng.choice([-1, 1], len(pos)))
        ev = cc.detect_clicks(x, SR)
        self.assertGreaterEqual(recall(ev, pos), 0.95)
        self.assertLessEqual(len(ev) - len(pos), 2)

    def test_event_fields_width_amplitude_and_offset(self):
        x = sine(2.0, seed=6)
        x[24000:24004] += 0.3                                    # 4 samples, 0.3
        ev = cc.detect_clicks(x, SR, block_size=BLOCK)
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertLessEqual(abs(e["start"] - 24000), 1)
        self.assertIn(e["width"], (3, 4, 5))
        self.assertAlmostEqual(e["amplitude"], 0.3, delta=0.06)
        self.assertEqual(e["block_offset"], e["start"] % BLOCK)
        self.assertAlmostEqual(e["time_s"], e["start"] / SR)
        for k in ("end", "score", "hf_db"):
            self.assertIn(k, e)
        self.assertGreater(e["score"], cc.CLICK_K)

    def test_speech_onset_is_not_a_click(self):
        x = np.zeros(SR) + np.random.default_rng(7).normal(0, NOISE, SR)
        t = np.arange(SR // 2) / SR
        x[SR // 4:SR // 4 + len(t)] += 0.2 * np.sin(2 * np.pi * 200 * t)      # starts abruptly
        self.assertEqual(cc.detect_clicks(x, SR), [])

    def test_tiny_input(self):
        self.assertEqual(cc.detect_clicks(np.zeros(5), SR), [])


class BlockAlignmentTests(unittest.TestCase):
    """Threshold (2): block-aligned clicks -> clustered; random clicks -> not clustered."""

    def test_clicks_exactly_on_block_boundaries_cluster(self):
        x = sine(20.0, seed=8)
        blocks = np.arange(100, 20 * SR // BLOCK - 100, 200)[:30]
        pos = blocks * BLOCK
        inject_clicks(x, pos, [2] * len(pos), [0.2] * len(pos))
        ev = cc.detect_clicks(x, SR)
        al = cc.block_alignment([e["start"] for e in ev], BLOCK)
        self.assertGreaterEqual(al["n"], 25)
        self.assertTrue(al["clustered"])
        self.assertTrue(al["at_block_start"])
        self.assertGreater(al["R"], 0.9)
        self.assertLess(al["p_value"], 1e-3)

    def test_fixed_offset_inside_block_clusters_but_is_not_block_start(self):
        pos = np.arange(30) * 5000 * BLOCK + 40
        al = cc.block_alignment(pos, BLOCK)
        self.assertTrue(al["clustered"])
        self.assertFalse(al["at_block_start"])
        self.assertAlmostEqual(al["preferred_offset"], 40.0, delta=1.0)

    def test_random_clicks_do_not_cluster(self):
        for seed in range(10):
            rng = np.random.default_rng(100 + seed)
            pos = rng.integers(0, 60 * SR, 40)
            al = cc.block_alignment(pos, BLOCK)
            self.assertFalse(al["clustered"], "seed %d: R=%.2f p=%.3g" % (seed, al["R"], al["p_value"]))

    def test_too_few_events_never_cluster(self):
        self.assertFalse(cc.block_alignment([0, 128, 256], BLOCK)["clustered"])
        self.assertEqual(cc.block_alignment([], BLOCK)["n"], 0)

    def test_first_block_start_shifts_the_offsets(self):
        pos = np.arange(20) * 1280 + 7
        al = cc.block_alignment(pos, BLOCK, first_block_start=7)
        self.assertTrue(al["at_block_start"])


class DropoutTests(unittest.TestCase):
    """Threshold (3): a zero run and a repeated-sample run inside a signal are found."""

    def test_zero_run_and_repeat_run_found_with_lengths(self):
        x = sine(4.0, seed=9)
        x[48000:48020] = 0.0                                     # 20 zeros
        x[96000:96030] = x[96000]                                # 30 repeats of one value
        d = cc.detect_dropouts(x, SR, block_size=BLOCK)
        kinds = {e["kind"]: e for e in d}
        self.assertEqual(set(kinds), {"zero", "repeat"})
        self.assertEqual(kinds["zero"]["start"], 48000)
        self.assertEqual(kinds["zero"]["length"], 20)
        self.assertEqual(kinds["repeat"]["start"], 96000)
        self.assertEqual(kinds["repeat"]["length"], 30)
        self.assertEqual(kinds["zero"]["block_offset"], 48000 % BLOCK)

    def test_digital_silence_is_not_a_dropout(self):
        x = np.zeros(SR)
        x[:SR // 4] = 0.3 * np.sin(2 * np.pi * 440 * np.arange(SR // 4) / SR)
        self.assertEqual(cc.detect_dropouts(x, SR), [])
        self.assertEqual(len(cc.detect_dropouts(np.zeros(SR), SR, include_silence=True)), 1)

    def test_short_runs_ignored(self):
        x = sine(1.0, seed=10)
        x[1000:1004] = 0.0
        self.assertEqual(cc.detect_dropouts(x, SR), [])

    def test_dropout_edges_are_tagged_not_counted_as_clicks(self):
        x = sine(4.0, seed=11)
        x[48000:48064] = 0.0
        rep = cc.analyze(x, SR, block_size=BLOCK)
        self.assertEqual(rep["n_dropouts"], 1)
        self.assertEqual(rep["n_clicks"], 0)
        self.assertTrue(all(c["in_dropout"] for c in rep["clicks"]))


class ClippingTests(unittest.TestCase):
    """Threshold (4): samples held at +/- full scale are reported with run lengths."""

    def test_runs_reported_with_lengths_and_signs(self):
        x = sine(1.0, a=0.2, seed=12)
        x[1000:1005] = 1.0
        x[5000:5012] = -1.0
        x[9000] = 1.0                                            # single sample: below min_run
        c = cc.detect_clipping(x)
        self.assertEqual(c["n_runs"], 2)
        self.assertEqual([r["length"] for r in c["runs"]], [5, 12])
        self.assertEqual([r["sign"] for r in c["runs"]], [1, -1])
        self.assertEqual(c["max_run"], 12)
        self.assertEqual(c["n_samples"], 18)

    def test_hard_clipped_sine(self):
        x = np.clip(1.5 * np.sin(2 * np.pi * 100 * np.arange(SR) / SR), -1.0, 1.0)
        c = cc.detect_clipping(x)
        self.assertEqual(c["n_runs"], 200)                       # 2 per cycle, 100 cycles
        self.assertGreater(c["max_run"], 10)

    def test_no_clipping(self):
        c = cc.detect_clipping(sine(1.0, a=0.5))
        self.assertEqual((c["n_runs"], c["n_samples"]), (0, 0))


class HumTests(unittest.TestCase):
    """Threshold (5): 50 and 60 Hz hum with harmonics found by hum_peaks."""

    def _hum(self, base, amps=(1e-3, 6e-4, 4e-4, 3e-4)):
        x = silence(6.0, seed=13)
        t = np.arange(len(x)) / SR
        for h, a in enumerate(amps, start=1):
            x += a * np.sin(2 * np.pi * base * h * t + h)
        return x

    def test_50_hz_hum(self):
        h = cc.hum_peaks(self._hum(50), SR)
        self.assertEqual(h["mains_hz"], 50)
        freqs = [p["freq"] for p in h["peaks"] if p["base"] == 50]
        for f in (50, 100, 150, 200):
            self.assertTrue(any(abs(q - f) < 1.0 for q in freqs), f)
        self.assertAlmostEqual(h["strongest_dbfs"], -60.0, delta=1.5)

    def test_60_hz_hum(self):
        h = cc.hum_peaks(self._hum(60), SR)
        self.assertEqual(h["mains_hz"], 60)
        freqs = [p["freq"] for p in h["peaks"] if p["base"] == 60]
        for f in (60, 120, 180, 240):
            self.assertTrue(any(abs(q - f) < 1.0 for q in freqs), f)

    def test_hum_without_fundamental(self):
        h = cc.hum_peaks(self._hum(50, amps=(0.0, 6e-4, 0.0, 3e-4)), SR)
        self.assertEqual(h["mains_hz"], 50)

    def test_noise_and_music_are_not_hum(self):
        self.assertIsNone(cc.hum_peaks(silence(6.0), SR)["mains_hz"])
        self.assertIsNone(cc.hum_peaks(sine(6.0, f=440.0), SR)["mains_hz"])

    def test_short_audio(self):
        self.assertIsNone(cc.hum_peaks(silence(0.5), SR)["mains_hz"])


class DcAndNoiseTests(unittest.TestCase):
    """Threshold (6): DC offset and noise floor in dBFS within 1 dB of the truth."""

    def test_dc_offset_within_1_db(self):
        for dc in (0.002, 0.01, -0.03):
            x = silence(5.0, seed=14) + dc
            r = cc.dc_and_noise_floor(x, SR)
            self.assertAlmostEqual(r["dc_dbfs"], 20 * np.log10(abs(dc)), delta=1.0)
            self.assertAlmostEqual(r["dc"], dc, delta=abs(dc) * 0.1)

    def test_noise_floor_within_1_db_with_loud_parts(self):
        for sigma in (1e-4, 3e-4, 2e-3):
            x = silence(20.0, noise=sigma, seed=15)
            x[5 * SR:8 * SR] += 0.3 * np.sin(2 * np.pi * 300 * np.arange(3 * SR) / SR)
            x += 0.01                                            # DC must not count as noise
            r = cc.dc_and_noise_floor(x, SR)
            self.assertAlmostEqual(r["noise_floor_dbfs"], 20 * np.log10(sigma), delta=1.0)

    def test_digital_silence_excluded(self):
        x = np.zeros(SR * 4)
        x[SR:2 * SR] = np.random.default_rng(16).normal(0, 1e-3, SR)
        r = cc.dc_and_noise_floor(x, SR)
        self.assertAlmostEqual(r["digital_silence_fraction"], 0.75, delta=0.05)
        self.assertAlmostEqual(r["noise_floor_dbfs"], -60.0, delta=1.0)

    def test_quiet_parts_flag(self):
        self.assertFalse(cc.dc_and_noise_floor(sine(5.0), SR)["quiet_parts"])      # steady tone
        x = silence(10.0)
        x[SR:3 * SR] += 0.3 * np.sin(2 * np.pi * 300 * np.arange(2 * SR) / SR)
        self.assertTrue(cc.dc_and_noise_floor(x, SR)["quiet_parts"])

    def test_all_zero_file(self):
        r = cc.dc_and_noise_floor(np.zeros(SR), SR)
        self.assertIsNone(r["noise_floor_dbfs"])


class BlockTableTests(unittest.TestCase):
    def test_events_next_to_late_blocks_are_linked(self):
        late = np.arange(50, 1000, 50)
        tb = make_blocks(60 * SR, BLOCK, late_idx=late)
        ev = late * BLOCK + 10
        c = cc.correlate_with_blocks(ev, tb, sr=SR)
        self.assertEqual(c["n_late"], len(late))
        self.assertEqual(c["near_late"], len(ev))
        self.assertTrue(c["linked"])
        self.assertLess(c["p_value"], 1e-6)

    def test_event_in_block_after_a_late_one_counts(self):
        tb = make_blocks(10 * SR, BLOCK, late_idx=[100, 200, 300])
        c = cc.correlate_with_blocks([101 * BLOCK + 5, 201 * BLOCK, 301 * BLOCK + 1], tb, sr=SR)
        self.assertEqual(c["near_any"], 3)

    def test_random_events_are_not_linked(self):
        tb = make_blocks(60 * SR, BLOCK, late_idx=[100, 900, 2000])
        rng = np.random.default_rng(17)
        c = cc.correlate_with_blocks(rng.integers(0, 60 * SR, 20), tb, sr=SR)
        self.assertFalse(c["linked"])

    def test_status_flags_and_adc_gaps(self):
        nb = 2000
        adc = np.arange(nb) * BLOCK / SR
        adc[1000:] += 0.01                                       # 10 ms gap before block 1000
        tb = {"start": np.arange(nb) * BLOCK, "frames": np.full(nb, BLOCK),
              "status": np.where(np.arange(nb) == 500, 4, 0), "adc_time": adc}
        c = cc.correlate_with_blocks([500 * BLOCK, 1000 * BLOCK, 1001 * BLOCK], tb, sr=SR)
        self.assertEqual(c["n_status"], 1)
        self.assertEqual(c["n_gap"], 1)
        self.assertEqual(c["near_status"], 1)
        self.assertEqual(c["near_gap"], 2)

    def test_table_formats(self):
        rows = [{"start": i * BLOCK, "frames": BLOCK, "cb_ms": 0.5, "status": 0} for i in range(100)]
        rows[10]["status"] = 1
        self.assertEqual(cc.correlate_with_blocks([10 * BLOCK], rows, sr=SR)["n_status"], 1)
        arr = np.zeros(100, dtype=[("start", "i8"), ("frames", "i8"), ("late", "i1")])
        arr["start"] = np.arange(100) * BLOCK
        arr["frames"] = BLOCK
        arr["late"][5] = 1
        self.assertEqual(cc.correlate_with_blocks([5 * BLOCK], arr, sr=SR)["n_late"], 1)
        only_block = {"cb_ms": np.full(100, 0.5)}
        self.assertEqual(cc.correlate_with_blocks([5], only_block, sr=SR, block_size=BLOCK)["n_blocks"], 100)

    def test_none_table(self):
        self.assertIsNone(cc.correlate_with_blocks([1, 2], None))


class FeatureAndIoTests(unittest.TestCase):
    def test_ms_features_rows_and_values(self):
        x = np.zeros(SR)
        t = np.arange(SR) / SR
        x[:] = 0.5 * np.sin(2 * np.pi * 3000 * t) + 0.1
        x[24000:24003] = 1.0                                      # three clipped samples
        f = cc.ms_features(x, SR)
        self.assertEqual(len(f["peak"]), 1000)                    # one row per millisecond
        self.assertEqual(f["band_db"].shape, (1000, 8))
        self.assertAlmostEqual(f["dc"][100], 0.1, delta=0.02)
        self.assertAlmostEqual(f["peak"][100], 0.6, delta=0.02)
        self.assertAlmostEqual(f["rms"][100], np.sqrt(0.5 * 0.25 + 0.01), delta=0.02)
        self.assertEqual(int(f["clip_count"][500]), 3)
        self.assertEqual(int(f["clip_count"][100]), 0)
        self.assertAlmostEqual(f["dominant_hz"][100], 3000, delta=500)
        self.assertLess(f["hf_ratio"][100], 0.2)
        self.assertGreater(f["max_step"][500], 0.35)
        self.assertGreater(f["zero_crossings"][100], 2)
        rows = cc.features_to_rows(f)
        self.assertEqual(len(rows), 1000)
        self.assertIn("band7_db", rows[0])

    def test_click_has_high_hf_ratio_and_step(self):
        x = sine(1.0, seed=18)
        x[20000] += 0.5
        f = cc.ms_features(x, SR)
        row = 20000 // 48
        self.assertGreater(f["hf_ratio"][row], 0.02)
        self.assertGreater(f["hf_ratio"][row], 50 * np.median(f["hf_ratio"]))
        self.assertGreater(f["max_step"][row], 0.4)
        self.assertGreater(f["max_step"][row], 20 * np.median(f["max_step"]))

    def test_ms_features_short(self):
        self.assertEqual(len(cc.ms_features(np.zeros(10), SR)["peak"]), 0)

    def test_load_audio_roundtrip_and_channels(self):
        import soundfile as sf
        x = sine(0.5, seed=19)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.wav")
            sf.write(p, x, SR, subtype="FLOAT")
            y, sr = cc.load_audio(p)
            self.assertEqual(sr, SR)
            self.assertLess(np.max(np.abs(x - y)), 1e-6)
            st = os.path.join(d, "s.wav")
            sf.write(st, np.stack([x, 0 * x], axis=1), SR, subtype="FLOAT")
            self.assertLess(np.max(np.abs(cc.load_audio(st)[0] - x / 2)), 1e-6)
            self.assertLess(np.max(np.abs(cc.load_audio(st, channel=0)[0] - x)), 1e-6)


class VerdictTests(unittest.TestCase):
    """Threshold (7): verdict() gives the expected hypothesis, with evidence lines and a
    next test, for five scenarios."""

    def assert_complete(self, v, top):
        self.assertEqual(v["top"], top)
        h = v["hypotheses"][0]
        self.assertEqual(h["name"], top)
        self.assertIn(h["confidence"], ("low", "medium", "high"))
        self.assertTrue(len(h["evidence"]) >= 1 and all(isinstance(s, str) and s for s in h["evidence"]))
        self.assertTrue(isinstance(h["next_test"], str) and len(h["next_test"]) > 20)
        self.assertIn("numbers", v["disclaimer"])
        self.assertTrue(v["summary"])

    def test_scenario_1_clean(self):
        x = sine(20.0, seed=20)
        rep = cc.analyze(x, SR, block_size=BLOCK,
                         blocks_table=make_blocks(len(x), BLOCK), meta={"source": "processed"})
        v = cc.verdict(rep)
        self.assert_complete(v, "clean")
        self.assertEqual(v["confidence"], "high")
        self.assertEqual(len(v["hypotheses"]), 1)

    def test_steady_tone_gives_no_noise_floor_note(self):
        v = cc.verdict(cc.analyze(sine(10.0, seed=29), SR, block_size=BLOCK))
        self.assertFalse(any("Noise floor" in n for n in v["notes"]))
        v = cc.verdict(cc.analyze(silence(5.0, noise=3e-3, seed=29), SR, meta={"silent_input": True}))
        self.assertTrue(any("Noise floor" in n for n in v["notes"]))

    def test_scenario_2_hardware_like_random_clicks_in_silence(self):
        rng = np.random.default_rng(21)
        x = silence(60.0, seed=21)
        pos, w, a = random_clicks(rng, len(x), 15)
        pos = pos + rng.integers(0, 4000, len(pos)) % 3000       # random block offsets
        inject_clicks(x, pos, w, a)
        rep = cc.analyze(x, SR, block_size=BLOCK, blocks_table=make_blocks(len(x), BLOCK),
                         meta={"source": "raw", "effects_off": True, "monitoring_off": True,
                               "silent_input": True})
        v = cc.verdict(rep)
        self.assert_complete(v, "hardware_or_driver_input")
        self.assertIn(v["confidence"], ("medium", "high"))
        self.assertFalse(rep["alignment"]["clustered"])
        self.assertFalse(rep["blocks"]["linked"])
        self.assertNotIn("software_scheduling", [h["name"] for h in v["hypotheses"]])

    def test_scenario_2b_without_conditions_or_timing_confidence_is_low(self):
        rng = np.random.default_rng(22)
        x = sine(30.0, seed=22)
        pos, w, a = random_clicks(rng, len(x), 10)
        inject_clicks(x, pos, w, a)
        v = cc.verdict(cc.analyze(x, SR, block_size=BLOCK))
        self.assertEqual(v["top"], "hardware_or_driver_input")
        self.assertEqual(v["confidence"], "low")

    def test_scenario_3_block_aligned_clicks_with_late_blocks(self):
        x = sine(30.0, seed=23)
        blocks = np.arange(200, 30 * SR // BLOCK - 200, 700)[:20]
        inject_clicks(x, blocks * BLOCK, [2] * len(blocks), [0.15] * len(blocks))
        tb = make_blocks(len(x), BLOCK, late_idx=blocks, status_idx=blocks[::3])
        rep = cc.analyze(x, SR, block_size=BLOCK, blocks_table=tb,
                         meta={"source": "processed", "effects_off": False})
        v = cc.verdict(rep)
        self.assert_complete(v, "software_scheduling")
        self.assertEqual(v["confidence"], "high")
        self.assertTrue(rep["alignment"]["at_block_start"])
        self.assertTrue(rep["blocks"]["linked"])
        self.assertNotIn("hardware_or_driver_input", [h["name"] for h in v["hypotheses"]])
        self.assertTrue(any("late block" in n for n in v["notes"]))

    def test_scenario_3b_aligned_without_timing_table_is_medium(self):
        x = sine(30.0, seed=24)
        blocks = np.arange(200, 30 * SR // BLOCK - 200, 700)[:20]
        inject_clicks(x, blocks * BLOCK, [2] * len(blocks), [0.15] * len(blocks))
        v = cc.verdict(cc.analyze(x, SR, block_size=BLOCK))
        self.assertEqual(v["top"], "software_scheduling")
        self.assertEqual(v["confidence"], "medium")

    def test_scenario_4_clipping(self):
        t = np.arange(10 * SR) / SR
        x = np.clip(1.5 * np.sin(2 * np.pi * 220 * t), -1.0, 1.0) + 0.0
        rep = cc.analyze(x, SR, block_size=BLOCK, meta={"source": "raw"})
        v = cc.verdict(rep)
        self.assert_complete(v, "gain_staging")
        self.assertEqual(v["confidence"], "high")
        self.assertIn("full scale", v["hypotheses"][0]["evidence"][0])

    def test_scenario_5_dsp_only_clicks(self):
        raw = sine(30.0, seed=25)
        proc = raw.copy()
        rng = np.random.default_rng(25)
        pos, w, a = random_clicks(rng, len(proc), 12)
        inject_clicks(proc, pos, w, a)
        rep = cc.analyze(proc, SR, block_size=BLOCK, raw=raw,
                         meta={"source": "processed", "effects_off": False})
        v = cc.verdict(rep)
        self.assert_complete(v, "software_dsp")
        self.assertIn(v["confidence"], ("medium", "high"))
        self.assertEqual(rep["compare"]["raw"], 0)
        self.assertGreaterEqual(rep["compare"]["processed_only"], 11)
        self.assertNotIn("hardware_or_driver_input", [h["name"] for h in v["hypotheses"]])

    def test_clicks_in_both_raw_and_processed_are_not_dsp(self):
        base = sine(30.0, seed=26)
        rng = np.random.default_rng(26)
        pos, w, a = random_clicks(rng, len(base), 10)
        inject_clicks(base, pos, w, a)
        raw, proc = base[20:], base[:-20]                        # processed track lags 20 samples
        rep = cc.analyze(proc, SR, block_size=BLOCK, raw=raw, meta={"source": "processed", "effects_off": False})
        v = cc.verdict(rep)
        self.assertEqual(rep["compare"]["processed_only"], 0)
        self.assertEqual(v["top"], "hardware_or_driver_input")

    def test_hum_and_dc_point_to_electrical(self):
        x = silence(8.0, seed=27) + 0.02
        t = np.arange(len(x)) / SR
        for h in (1, 2, 3):
            x += 1e-3 * np.sin(2 * np.pi * 50 * h * t)
        v = cc.verdict(cc.analyze(x, SR, meta={"source": "raw"}))
        self.assertEqual(v["top"], "electrical")
        self.assertEqual(v["confidence"], "high")

    def test_few_events_give_no_verdict(self):
        x = sine(10.0, seed=28)
        x[100000] += 0.4
        x[300000] += 0.4
        v = cc.verdict(cc.analyze(x, SR, block_size=BLOCK))
        self.assertEqual(v["top"], "clean")
        self.assertTrue(any("Fewer than" in s for s in v["hypotheses"][0]["evidence"]))

    def test_verdict_accepts_report_without_optional_parts(self):
        v = cc.verdict({"n_clicks": 0, "clicks_per_min": 0.0, "duration_s": 10.0})
        self.assertEqual(v["top"], "clean")


if __name__ == "__main__":
    unittest.main()
