"""Phase 0 baseline tests for project save/load and offline render.
Save/load needs the real `soundfile`; those tests are skipped without it."""
import os
import tempfile
import unittest
import numpy as np

from tests.fake_stream import make_engine, run_blocks
from track import Track

try:
    import soundfile as _sf
    HAVE_SF = hasattr(_sf, "__version__")
except Exception:
    HAVE_SF = False

if HAVE_SF or True:
    try:
        import project_io
    except Exception:  # soundfile missing entirely
        project_io = None

SR = 48000
BLK = 64


@unittest.skipIf(project_io is None, "project_io needs soundfile")
class RenderTests(unittest.TestCase):
    def test_render_matches_live_callback(self):
        e = make_engine(SR, BLK)
        data = (0.3 * np.sin(2 * np.pi * 220 * np.arange(BLK * 40) / SR)).astype(np.float32)
        t = Track("a", SR)
        t.load_from_array(data, 0)
        t.gain, t.pan = 0.8, -0.4
        e.add_track(t)
        e.play()
        l, r = run_blocks(e, np.zeros(BLK * 40, dtype=np.float32))
        stereo = project_io.render_mix(e.snapshot_tracks(), SR, master_gain=1.0,
                                       master_fx=e.master_fx_l, extra_tail_sec=0.1)
        n = len(l)
        np.testing.assert_allclose(stereo[:n, 0], l, atol=1e-5)
        np.testing.assert_allclose(stereo[:n, 1], r, atol=1e-5)

    def test_render_respects_solo_and_mute(self):
        e = make_engine(SR, BLK)
        a, b = Track("a", SR), Track("b", SR)
        a.load_from_array(np.full(1000, 0.2, dtype=np.float32), 0)
        b.load_from_array(np.full(1000, 0.4, dtype=np.float32), 0)
        b.solo = True
        out = project_io.render_mix([a, b], SR, extra_tail_sec=0.01)
        self.assertAlmostEqual(float(out[500, 0]), 0.4, places=4)   # rc10: soft_limit is transparent below 0.8


@unittest.skipUnless(HAVE_SF, "real soundfile not installed")
class SaveLoadTests(unittest.TestCase):
    def test_round_trip_audio_and_meta(self):
        e = make_engine(SR, BLK)
        t = Track("lead", SR)
        t.load_from_array(np.random.RandomState(3).randn(5000).astype(np.float32) * 0.2, 123)
        t.gain, t.pan, t.mute = 1.3, 0.25, True
        t.effects.reverb.enabled = True
        t.effects.reverb.room_size = 0.8
        e.add_track(t)
        e.master_gain = 0.7
        e.input_monitor_enabled = True
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.llproj")
            project_io.save_project(path, e)
            tracks, transport = project_io.load_project(path, SR)
        self.assertEqual(len(tracks), 1)
        t2 = tracks[0]
        np.testing.assert_allclose(t2.buffer, t.buffer, atol=1e-7)
        self.assertEqual((t2.name, t2.offset, t2.mute), ("lead", 123, True))
        self.assertAlmostEqual(t2.gain, 1.3)
        self.assertEqual(t2.effects.to_dict(), t.effects.to_dict())
        self.assertAlmostEqual(transport["master_gain"], 0.7)
        self.assertTrue(transport["input_monitor_enabled"])

    def test_missing_optional_keys_use_defaults(self):
        import json, zipfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "old.llproj")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("project.json", json.dumps({"tracks": []}))
            tracks, transport = project_io.load_project(path, SR)
        self.assertEqual(tracks, [])
        self.assertFalse(transport["loop_enabled"])
        self.assertEqual(transport["master_gain"], 1.0)


if __name__ == "__main__":
    unittest.main()
