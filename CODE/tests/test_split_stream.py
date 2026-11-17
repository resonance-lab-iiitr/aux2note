"""T030: SplitStream (separate exclusive input and output streams joined by a ring),
the 'split' setting, the ladder fallback, Debug / Lab counters and the Lab verdict.
No hardware: sounddevice is replaced by a fake module."""
import csv
import os
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

from tests import _stubs  # noqa: F401
import audio_engine
import split_stream
from split_stream import SplitStream, split_meta
import settings_store as ss
from stream_config import StreamConfig, build_ladder
import crackle_core as cc
import debug_log as dl

BLOCK = 160


class _FakeIn:
    samplerate = 48000.0
    latency = 0.004
    cpu_load = 0.01

    def __init__(self, **kw):
        self.kw = kw
        self.started = self.closed = False

    def start(self): self.started = True
    def stop(self): self.started = False
    def close(self): self.closed = True


_FakeOut = type("_FakeOut", (_FakeIn,), {})


def fake_sd():
    return types.SimpleNamespace(
        InputStream=_FakeIn, OutputStream=_FakeOut,
        WasapiSettings=lambda exclusive=False: types.SimpleNamespace(exclusive=exclusive))


class Harness:
    """Builds a SplitStream on the fake sd and drives its callbacks by hand."""

    def __init__(self, prefill=1, block=BLOCK):
        self.seen = []                                   # (indata copy, status) the engine callback got
        self.block = block
        with mock.patch.object(split_stream, "sd", fake_sd()):
            self.s = SplitStream(1, 2, 48000, block, 2, self.cb, prefill_blocks=prefill)
        self.n = 0

    def cb(self, indata, outdata, frames, time_info, status):
        self.seen.append(indata[:, 0].copy())
        outdata[:] = 0

    def feed(self, k=1):
        """Input callback k times; each block holds a ramp so the order can be checked."""
        for _ in range(k):
            x = np.zeros((self.block, 2), dtype=np.float32)
            x[:, 0] = np.arange(self.n * self.block, (self.n + 1) * self.block) + 1.0
            self.n += 1
            self.s._in_cb(x, self.block, None, None)

    def pull(self, k=1):
        for _ in range(k):
            self.s._out_cb(np.zeros((self.block, 2), dtype=np.float32), self.block, None, None)


class TestSplitStream(unittest.TestCase):
    def test_steady_delivery_has_no_underflow_and_keeps_order(self):
        h = Harness()
        h.feed(); h.pull()                       # primes (fill 1 block >= prefill)
        for _ in range(50):
            h.feed(); h.pull()
        st = h.s.stats()
        self.assertEqual((st["underflows"], st["overflows"], st["trims"]), (0, 0, 0))
        got = np.concatenate(h.seen[-20:])
        self.assertTrue(np.all(np.diff(got) == 1.0), "samples must arrive in order, none lost")

    def test_output_before_prefill_plays_silence_without_counting(self):
        h = Harness()
        h.pull(3)
        self.assertEqual(h.s.stats()["underflows"], 0)
        self.assertEqual(h.seen, [])             # engine callback not called before priming

    def test_late_input_gives_silent_block_and_counts_underflow(self):
        h = Harness()
        h.feed(); h.pull()
        h.pull()                                  # input did not deliver: ring empty
        self.assertEqual(h.s.stats()["underflows"], 1)
        self.assertTrue(np.all(h.seen[-1] == 0.0))
        self.assertEqual(h.s.stats()["out_blocks"], 2)

    def test_burst_delivery_is_absorbed_without_underflow(self):
        h = Harness(prefill=2)
        h.feed(2); h.pull()
        for _ in range(30):                       # input arrives in pairs, output one by one
            h.feed(2); h.pull(); h.pull()
        self.assertEqual(h.s.stats()["underflows"], 0)

    def test_burst_then_gap_counts_underflows(self):
        h = Harness(prefill=1)
        h.feed(); h.pull()
        h.pull(); h.pull()                        # input stalled for 2 blocks
        h.feed(2)
        self.assertEqual(h.s.stats()["underflows"], 2)

    def test_ring_overflow_is_counted_and_block_dropped(self):
        h = Harness()
        h.feed(split_stream.RING_BLOCKS)          # reader never runs
        self.assertEqual(h.s.stats()["overflows"], 0)
        h.feed(3)
        self.assertEqual(h.s.stats()["overflows"], 3)

    def test_clock_drift_trims_to_prefill(self):
        h = Harness()
        h.feed(); h.pull()
        h.feed(8)                                 # input ran ahead by more than prefill + 4 blocks
        h.pull()
        self.assertEqual(h.s.stats()["trims"], 1)

    def test_stats_fields(self):
        h = Harness(prefill=3)
        st = h.s.stats()
        self.assertEqual((st["split"], st["block"], st["prefill_blocks"], st["ring_blocks"]),
                         (True, BLOCK, 3, split_stream.RING_BLOCKS))

    def test_trace_file_and_summary_on_close(self):
        h = Harness()
        for _ in range(5):
            h.feed(); h.pull()
        with tempfile.TemporaryDirectory() as d:
            path = h.s.write_trace(d)
            with open(path) as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 10)
        self.assertEqual(set(rows[0]), {"t_ms", "kind", "fill_samples", "underflow", "adc_ms", "chk"})
        self.assertEqual({r["kind"] for r in rows}, {"in", "out"})
        with mock.patch.object(h.s, "write_trace"):
            h.s.close()
        self.assertTrue(h.s.summary.startswith("SPLIT STREAM: block 160, prefill 1, underflows 0"))

    def test_input_frame_and_repeat_counters(self):
        h = Harness()
        blk = np.full((BLOCK, 2), 0.25, dtype=np.float32)
        for _ in range(3):                       # identical non-silent blocks: 2 repeats
            h.s._in_cb(blk, BLOCK, types.SimpleNamespace(inputBufferAdcTime=1.0), None)
        h.s._in_cb(np.zeros((BLOCK, 2), dtype=np.float32), BLOCK, None, None)   # silence is never a repeat
        h.s._in_cb(np.zeros((BLOCK, 2), dtype=np.float32), BLOCK, None, None)
        st = h.s.stats()
        self.assertEqual(st["in_frames_total"], 5 * BLOCK)
        self.assertEqual(st["in_dup_blocks"], 2)
        for k in ("underflows", "overflows", "trims", "out_blocks", "in_blocks", "prefill_blocks", "ring_blocks"):
            self.assertIn(k, st)                 # old keys stay

    def test_replay_tool_counts_underflows_like_the_stream(self):
        from tools import split_replay
        kind = ["out", "in", "out", "out", "in", "in", "out"]
        t = list(range(len(kind)))
        n, under, trims, over = split_replay.replay(t, kind, BLOCK, 1)
        self.assertEqual((n, under, trims, over), (3, 1, 0, 0))

    def test_split_meta_is_a_difference(self):
        a = {"prefill_blocks": 1, "ring_blocks": 16, "underflows": 4, "overflows": 0, "trims": 1, "out_blocks": 100}
        b = dict(a, underflows=10, trims=3, out_blocks=400)
        m = split_meta(a, b)
        self.assertEqual((m["split_underflows"], m["split_trims"], m["split_out_blocks"]), (6, 2, 300))
        self.assertEqual(split_meta(a, None), {})


class TestSplitSetting(unittest.TestCase):
    def test_default_off_and_validated(self):
        v = ss.AUDIO_DEFAULTS_VERSION
        self.assertIs(ss.DEFAULT_SETTINGS["split"], True)
        self.assertIs(ss.sanitize({"audio_defaults": v, "split": False})["split"], False)
        self.assertIs(ss.sanitize({"audio_defaults": v, "split": True})["split"], True)
        self.assertIs(ss.sanitize({"audio_defaults": v, "split": "yes"})["split"], True)
        self.assertIn(160, ss.BLOCK_SIZES)

    def test_build_config_split_only_for_exclusive_wasapi(self):
        self.assertTrue(ss.build_config(ss.WASAPI_NAME, True, 48000, 160, 1, 2, split=True).split)
        self.assertFalse(ss.build_config(ss.WASAPI_NAME, False, 48000, 160, 1, 2, split=True).split)
        self.assertFalse(ss.build_config("MME", True, 48000, 160, 1, 2, split=True).split)

    def test_ladder_falls_back_to_shared_without_split(self):
        cfg = StreamConfig(api=ss.WASAPI_NAME, exclusive=True, sample_rate=48000, block_size=160,
                           in_device=1, out_device=2, split=True)
        ladder = build_ladder(cfg, tracks_exist=False, current_rate=48000)
        self.assertTrue(ladder[0].split)
        last = ladder[-1]
        self.assertFalse(last.exclusive)
        self.assertFalse(last.split)
        self.assertTrue(all(not s.split for s in ladder if not s.exclusive))

    def test_labels_show_split(self):
        cfg = StreamConfig(api=ss.WASAPI_NAME, exclusive=True, sample_rate=48000, block_size=160, split=True)
        self.assertIn("SPLIT", cfg.mode_label())
        self.assertIn("split", cfg.short_label())


class TestEngineUsesSplit(unittest.TestCase):
    def test_engine_opens_split_stream_and_reports_stats(self):
        made = {}

        class FakeSplit:
            def __init__(self, *a, **k):
                made["args"], made["kw"] = a, k
                self.latency = (0.005, 0.005)
                self.summary, self.trace_path = "", None
            def start(self): pass
            def stop(self): pass
            def close(self): self.summary = "SPLIT STREAM: x"
            def stats(self): return {"split": True, "prefill_blocks": 1, "ring_blocks": 16, "underflows": 3,
                                     "overflows": 0, "trims": 0, "out_blocks": 10, "in_blocks": 10}

        e = audio_engine.AudioEngine(sample_rate=48000, block_size=160)
        cfg = StreamConfig(api=ss.WASAPI_NAME, exclusive=True, sample_rate=48000, block_size=160,
                           in_device=1, out_device=2, split=True)
        with mock.patch.object(audio_engine, "SplitStream", FakeSplit), \
                mock.patch.object(audio_engine, "check_same_hostapi", return_value=None):
            e.open_stream(1, 2, cfg)
        self.assertIn("args", made)
        self.assertEqual(e.split_stats()["underflows"], 3)
        self.assertIn("3 underflows", dl.split_text(e))
        rows = dict(dl.engine_snapshot(e))
        self.assertIn("underflows 3", rows["split stream"])
        e.close_stream()
        self.assertIsNone(e.split_stats())
        self.assertEqual(dl.split_text(e), "-")


class TestLabVerdict(unittest.TestCase):
    def _report(self, meta):
        sr, n = 48000, 48000 * 5
        x = (0.3 * np.sin(2 * np.pi * 1000 * np.arange(n) / sr)).astype(np.float32)
        for b in range(10, n // BLOCK - 1, 5):          # zero runs of one block
            x[b * BLOCK:(b + 1) * BLOCK] = 0.0
        return cc.analyze(x, sr, block_size=BLOCK, blocks_table=None, meta=meta)

    def test_split_underflows_become_top_hypothesis_without_larger_block_advice(self):
        v = cc.verdict(self._report({"source": "raw", "split": True,
                                     "split_underflows": 300, "split_out_blocks": 1500}))
        self.assertEqual(v["top"], "split_handoff")
        self.assertEqual(v["confidence"], "high")
        for h in v["hypotheses"]:
            self.assertNotIn("larger block (256", h["next_test"])

    def test_no_split_hypothesis_without_counter(self):
        v = cc.verdict(self._report({"source": "raw"}))
        self.assertNotIn("split_handoff", [h["name"] for h in v["hypotheses"]])

    def test_few_underflows_are_only_a_note(self):
        v = cc.verdict(self._report({"source": "raw", "split": True,
                                     "split_underflows": 2, "split_out_blocks": 6000}))
        self.assertNotIn("split_handoff", [h["name"] for h in v["hypotheses"]])
        self.assertTrue(any("Split in/out" in n for n in v["notes"]))


if __name__ == "__main__":
    unittest.main()
