"""Phase 7 tests: one version number everywhere, project file stamp, %% fix,
soak tool smoke test (a few seconds of audio, checks it runs and finds no NaN)."""
import io
import json
import os
import re
import subprocess
import sys
import unittest
import zipfile

from tests import _stubs  # noqa: F401
from tests.fake_stream import make_engine
import version
import debug_log
import project_io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Versions(unittest.TestCase):
    def test_single_source(self):
        self.assertEqual(version.APP_VERSION, "2.0")
        self.assertEqual(debug_log.VERSION, version.APP_VERSION)

    def test_window_title_uses_version(self):
        with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("APP_VERSION", src)
        self.assertRegex(src, r"root\.title\(f\"\{APP_NAME\} \{APP_VERSION\}\"\)")

    def test_project_file_has_app_version(self):
        import tempfile
        eng = make_engine()
        path = os.path.join(tempfile.mkdtemp(), "t.llproj")
        project_io.save_project(path, eng)
        with zipfile.ZipFile(path) as zf:
            data = json.loads(zf.read("project.json"))
        self.assertEqual(data["app_version"], "2.0")
        self.assertEqual(data["version"], project_io.PROJECT_VERSION)  # format unchanged

    def test_old_file_without_app_version_loads(self):
        import tempfile
        eng = make_engine()
        path = os.path.join(tempfile.mkdtemp(), "old.llproj")
        project_io.save_project(path, eng)
        # strip the new key to imitate a v1.x file
        with zipfile.ZipFile(path) as zin:
            items = {n: zin.read(n) for n in zin.namelist()}
        d = json.loads(items["project.json"])
        d.pop("app_version")
        items["project.json"] = json.dumps(d).encode()
        with zipfile.ZipFile(path, "w") as zout:
            for n, b in items.items():
                zout.writestr(n, b)
        tracks, settings = project_io.load_project(path)  # must not raise
        self.assertEqual(tracks, [])


class LatencyLabPercent(unittest.TestCase):
    def test_no_double_percent_in_plain_prints(self):
        with open(os.path.join(ROOT, "latency_lab.py"), encoding="utf-8") as fh:
            src = fh.read()
        for line in src.splitlines():
            if line.strip().startswith("print(") and "%%" in line:
                self.assertIn(" % ", line, f"plain print with %%: {line.strip()}")


class SoakSmoke(unittest.TestCase):
    def test_offline_soak_runs(self):
        # 0.5 min is enough to run all 4 takes (36 s of timeline needs 0.6 min)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "soak_test.py"),
                            "--offline", "--minutes", "0.65", "--block", "256"],
                           capture_output=True, text=True, timeout=120, cwd=ROOT)
        out = r.stdout
        self.assertIn("=== RESULT ===", out, out + r.stderr)
        self.assertIn("takes_done     True", out)
        self.assertNotIn("NaN", out)
        # verdict depends on CPU speed (pass/fail is judged on the real PC), so not asserted


class SoakTuning(unittest.TestCase):
    def test_apply_tuning_switch_interval(self):
        import argparse
        sys_old = sys.getswitchinterval()
        try:
            from tools.soak_test import apply_tuning
            out = apply_tuning(argparse.Namespace(switch_interval=0.001, priority=None, timer1=False))
            self.assertAlmostEqual(sys.getswitchinterval(), 0.001, places=4)
            self.assertIn("switch-interval 0.001", out[0])
            self.assertEqual(apply_tuning(argparse.Namespace(switch_interval=None, priority=None, timer1=False)), [])
        finally:
            sys.setswitchinterval(sys_old)


class SoakScenarios(unittest.TestCase):
    def _on(self, fx):
        from tools.soak_test import make_engine
        eng, tracks = make_engine(48000, 64, offline=True, fx=fx)
        names = ("eq", "compressor", "distortion", "delay", "reverb")
        return [[n for n in names if getattr(t.effects, n).enabled] for t in tracks], eng

    def test_none_has_no_track_effects(self):
        per_track, _ = self._on("none")
        self.assertTrue(all(p == [] for p in per_track))

    def test_typical(self):
        per_track, _ = self._on("typical")
        self.assertEqual(per_track[0], ["eq", "compressor", "reverb"])
        self.assertEqual(per_track[1], ["eq", "compressor"])

    def test_all(self):
        per_track, eng = self._on("all")
        self.assertTrue(all(len(p) == 5 for p in per_track))
        self.assertTrue(eng.master_fx_r.reverb.enabled)


class DocsPresent(unittest.TestCase):
    def test_release_files(self):
        for f in ("README.md", "CHANGELOG.md", "run_looper.bat", "docs/QA_RESULTS.md",
                  "latency_lab.py", "requirements.txt"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, f)), f)

    def test_changelog_has_entry_for_every_phase(self):
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
            cl = fh.read()
        self.assertRegex(cl, r"## v?2\.0")
        for ph in ("Phase 1", "Phase 2", "Phase 3", "Phase 4a", "Phase 4b",
                   "Phase 5", "Phase 6", "Phase 7"):
            self.assertIn(ph, cl, ph)


if __name__ == "__main__":
    unittest.main()
