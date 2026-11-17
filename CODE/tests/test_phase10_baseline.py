"""Phase 10 (T023): software-only baseline for the crackle lab.

A standard project (3 tracks of sine / speech-like material, every effect on,
master FX on) is rendered offline with project_io.render_mix and analysed with
crackle_report.run. No sound card is involved, so any click found here is made
by the DSP alone.

FINDING recorded while writing this test (see the T023 session note):
render_mix (and the live callback, audio_engine.py line ~592) only runs a
track's effect chain when the block holds a non-zero sample. When a clip ends
in exact digital silence the track's delay / reverb tail is cut, and an effect
on the master bus repeats that cut as clicks (6-7 clicks, 350 ms apart, in the
rendered tail). `keep_alive=True` adds a 1e-9 floor under the material so the
chains keep running; that is the clean baseline. `keep_alive=False` is the
case that shows the finding. Nothing here changes any .py file.

Run from CODE/:  python3.12 -m unittest tests.test_phase10_baseline
Make the sample packs: python3.12 -m tests.test_phase10_baseline <out_dir>
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

import crackle_report
from tests.test_phase10_crackle_core import SR, inject_clicks, sine, speech_like
from track import Track
from effects import EffectsChain

try:
    import soundfile as sf
    import project_io
except Exception:                                     # soundfile missing entirely
    sf = None
    project_io = None

ALL5 = ("eq", "compressor", "distortion", "delay", "reverb")
DUR = 8.0
BLOCK = 128
FLOOR = 1e-9                                          # keeps effect chains running after a clip ends


def _fade(x, ms=100):
    n = int(ms / 1000.0 * SR)
    x = x.copy()
    ramp = np.linspace(0.0, 1.0, n)
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def standard_project(keep_alive=True, dur=DUR):
    """3 tracks, every effect on, master FX on. Distortion is mild (drive/mix 0.3)
    and track gain 0.3 so the baseline does not clip: the distortion output is
    normalised to full scale at default settings (a gain-staging fact, not a click)."""
    sigs = [_fade(sine(dur, 220.0, 0.2, seed=1)),
            _fade(speech_like(dur, seed=3)),
            _fade(sine(dur, 330.0, 0.15, seed=2))]
    tracks = []
    for i, s in enumerate(sigs):
        if keep_alive:
            s = np.concatenate([s, np.full(int(4 * SR), FLOOR)])
        t = Track("Base %d" % (i + 1), SR)
        t.load_from_array(s.astype(np.float32), 0)
        for name in ALL5:
            getattr(t.effects, name).enabled = True
        t.effects.distortion.drive = 0.3
        t.effects.distortion.mix = 0.3
        t.gain = 0.3
        t.pan = (-0.5, 0.0, 0.5)[i]
        tracks.append(t)
    master = EffectsChain(SR)
    for name in ALL5:
        getattr(master, name).enabled = True
    master.distortion.drive = 0.3
    master.distortion.mix = 0.3
    return tracks, master


def render_standard(keep_alive=True, dur=DUR):
    tracks, master = standard_project(keep_alive, dur)
    return project_io.render_mix(tracks, SR, master_fx=master, extra_tail_sec=3.0)


def analyse(x, out_dir, make_png=False, **kw):
    path = out_dir + ".wav"
    sf.write(path, np.asarray(x, dtype=np.float32), SR, subtype="FLOAT")
    return crackle_report.run(path, out_dir=out_dir, make_png=make_png, block_size=BLOCK, **kw)


@unittest.skipIf(project_io is None or sf is None, "needs soundfile")
class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.alive = render_standard(True)
        cls.silent = render_standard(False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _counts(self, stereo, tag):
        out = {}
        for ch in (0, 1):
            r = analyse(stereo[:, ch], os.path.join(self.tmp.name, "%s_%d" % (tag, ch)))
            out[ch] = r["report"]["counts"]
        return out

    def test_standard_project_has_zero_clicks_and_zero_dropouts(self):
        """(1) Effects chains kept running: the DSP alone must not make clicks."""
        self.assertLess(float(np.max(np.abs(self.alive))), 0.95)       # no clipping in the baseline
        for ch, c in self._counts(self.alive, "alive").items():
            self.assertEqual(c["clicks"], 0, "channel %d: %s" % (ch, c))
            self.assertEqual(c["dropouts"], 0, "channel %d: %s" % (ch, c))
            self.assertEqual(c["clip_runs"], 0, "channel %d: %s" % (ch, c))

    def test_baseline_can_fail_when_clicks_are_injected(self):
        """(2) The same render with 12 clicks at block starts is reported with clicks."""
        x = self.alive[:, 0].astype(np.float64).copy()
        pos = [BLOCK * k for k in range(100, 100 + 12 * 300, 300)]     # block starts, 300 blocks apart
        inject_clicks(x, pos, [3] * len(pos), [0.2] * len(pos), "rect")
        r = analyse(x, os.path.join(self.tmp.name, "inj"))["report"]
        self.assertGreaterEqual(r["counts"]["clicks"], 10)             # >= 10 of 12 found

    def test_finding_exact_silence_after_a_clip_does_not_beat_the_floor(self):
        """FINDING: ending a clip in exact zeros cuts the effect tails. Recorded, not hidden.
        Passes now (more clicks with exact zeros) and still passes once the engine is fixed."""
        alive = self._counts(self.alive, "a2")
        silent = self._counts(self.silent, "s2")
        n_alive = sum(c["clicks"] for c in alive.values())
        n_silent = sum(c["clicks"] for c in silent.values())
        self.assertGreaterEqual(n_silent, n_alive)
        self.last_finding = {"clicks_with_floor": n_alive, "clicks_with_exact_silence": n_silent}


# --------------------------------------------------------------------------- #
# Sample packs for DELIVERABLES (run as a module)
# --------------------------------------------------------------------------- #
def make_samples(out_root):
    os.makedirs(out_root, exist_ok=True)
    base = standard_project(True)
    result = {"note": "software-only baseline: 3 tracks, every effect on, master FX on, rendered with render_mix"}
    alive = render_standard(True)
    silent = render_standard(False)

    def counts(stereo, tag):
        res = {}
        for ch, name in ((0, "left"), (1, "right")):
            r = analyse(stereo[:, ch], os.path.join(out_root, "_tmp_" + tag + name))
            c = r["report"]["counts"]
            res[name] = {k: c[k] for k in ("clicks", "dropouts", "clip_runs")}
        return res

    result["baseline_effect_tails_kept_alive"] = counts(alive, "a")
    result["finding_clip_ends_in_exact_silence"] = counts(silent, "s")
    for f in os.listdir(out_root):
        if f.startswith("_tmp_"):
            p = os.path.join(out_root, f)
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            else:
                os.remove(p)

    # Sample 1: 14 clicks at block starts (block 128) on a clean 440 Hz sine
    x = sine(5.0, 440.0, 0.2, seed=4)
    pos = [BLOCK * k for k in range(100, 100 + 14 * 120, 120)]
    inject_clicks(x, pos, [3] * len(pos), [0.2] * len(pos), "rect")
    r1 = analyse(x, os.path.join(out_root, "sample_clicks_at_block_starts"), n_excerpts=2)
    # Sample 2: DC offset + 50 Hz hum
    t = np.arange(int(5 * SR)) / SR
    y = sine(5.0, 440.0, 0.2, seed=5) + 0.02 + 0.01 * np.sin(2 * np.pi * 50.0 * t)
    r2 = analyse(y, os.path.join(out_root, "sample_dc_and_hum"), n_excerpts=2)
    result["sample_clicks_at_block_starts"] = {"counts": r1["report"]["counts"],
                                               "top": r1["verdict"].get("top")}
    result["sample_dc_and_hum"] = {"counts": r2["report"]["counts"], "top": r2["verdict"].get("top")}
    with open(os.path.join(out_root, "baseline_result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
        fh.write("\n")
    import shutil
    for f in os.listdir(out_root):                      # keep only report.md + analysis_pack.zip per sample
        p = os.path.join(out_root, f)
        if f.endswith(".wav"):
            os.remove(p)
        elif os.path.isdir(p):
            for g in os.listdir(p):
                if g not in ("report.md", "analysis_pack.zip"):
                    q = os.path.join(p, g)
                    shutil.rmtree(q) if os.path.isdir(q) else os.remove(q)
    return result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(make_samples(sys.argv[1]), indent=1))
    else:
        unittest.main()
