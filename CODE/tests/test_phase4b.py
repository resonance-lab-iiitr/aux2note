"""Phase 4b tests: settings.json, device helpers, panel -> config, project
`audio` section, and a GUI smoke test (skipped where Tk or a display is
missing; it runs on the user's PC)."""
import json
import os
import tempfile
import unittest

from tests import _stubs  # noqa: F401
import settings_store as ss
from stream_config import WASAPI_NAME

try:
    import project_io
except Exception:
    project_io = None

IN = [(1, "ID 1: Mic (Realtek)  [MME]"), (5, "ID 5: Mic (Realtek)  [Windows WASAPI]"),
      (6, "ID 6: Line In  [Windows WASAPI]")]
OUT = [(2, "ID 2: Speakers (Realtek)  [MME]"), (7, "ID 7: Speakers (Realtek)  [Windows WASAPI]")]
ROWS = [{"id": 1, "name": "Mic (Realtek)", "is_default_in": True, "is_default_out": False},
        {"id": 2, "name": "Speakers (Realtek)", "is_default_in": False, "is_default_out": True}]


class SettingsFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "settings.json")

    def test_round_trip(self):
        s = dict(ss.DEFAULT_SETTINGS, driver="MME", exclusive=False, sample_rate=44100,
                 block_size=128, record_offset_ms=8.2, in_device="Mic", out_device="Spk")
        self.assertTrue(ss.save_settings(s, self.path))
        self.assertEqual(ss.load_settings(self.path), s)

    def test_missing_file_gives_defaults(self):
        self.assertEqual(ss.load_settings(self.path), ss.DEFAULT_SETTINGS)

    def test_broken_json_ignored(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(ss.load_settings(self.path), ss.DEFAULT_SETTINGS)

    def test_bad_values_fall_back_per_key(self):
        with open(self.path, "w") as f:
            json.dump({"sample_rate": 12345, "block_size": "64", "exclusive": "yes",
                       "record_offset_ms": 99999, "driver": "MME", "evil": 1}, f)
        got = ss.load_settings(self.path)
        self.assertEqual(got["sample_rate"], 48000)
        self.assertEqual(got["block_size"], ss.DEFAULT_SETTINGS["block_size"])
        self.assertTrue(got["exclusive"])
        self.assertEqual(got["record_offset_ms"], 0.0)
        self.assertEqual(got["driver"], "MME")
        self.assertNotIn("evil", got)

    def test_non_dict_json_ignored(self):
        with open(self.path, "w") as f:
            f.write("[1,2]")
        self.assertEqual(ss.load_settings(self.path), ss.DEFAULT_SETTINGS)

    def test_save_failure_does_not_raise(self):
        self.assertFalse(ss.save_settings({}, os.path.join(self.dir, "no", "such", "x.json")))


class DeviceHelperTests(unittest.TestCase):
    def test_driver_names_and_filter(self):
        self.assertEqual(ss.driver_names(IN + OUT), ["MME", "Windows WASAPI"])
        self.assertEqual([i for i, _ in ss.filter_by_driver(IN, WASAPI_NAME)], [5, 6])

    def test_name_and_id_parsing(self):
        self.assertEqual(ss.name_of(IN[1][1]), "Mic (Realtek)")
        self.assertEqual(ss.parse_device_id(IN[2][1]), 6)

    def test_preferred_matches_default_by_name(self):
        wasapi_in = ss.filter_by_driver(IN, WASAPI_NAME)
        self.assertEqual(ss.preferred_index(wasapi_in, ROWS, "is_default_in"), 0)
        wasapi_out = ss.filter_by_driver(OUT, WASAPI_NAME)
        self.assertEqual(ss.preferred_index(wasapi_out, ROWS, "is_default_out"), 0)

    def test_index_by_name(self):
        wasapi_in = ss.filter_by_driver(IN, WASAPI_NAME)
        self.assertEqual(ss.index_by_name(wasapi_in, "Line In"), 1)
        self.assertIsNone(ss.index_by_name(wasapi_in, "Gone"))
        self.assertIsNone(ss.index_by_name(wasapi_in, ""))


class ConfigTests(unittest.TestCase):
    def test_wasapi_exclusive(self):
        c = ss.build_config(WASAPI_NAME, True, "48000", "64", 5, 7)
        self.assertTrue(c.exclusive)
        self.assertEqual((c.sample_rate, c.block_size, c.in_device, c.out_device), (48000, 64, 5, 7))

    def test_exclusive_forced_off_for_other_drivers(self):
        self.assertFalse(ss.build_config("MME", True, 44100, 256, 1, 2).exclusive)

    def test_auto_choice(self):
        a = ss.auto_choice()
        self.assertEqual((a["driver"], a["exclusive"], a["sample_rate"], a["block_size"]),
                         (WASAPI_NAME, True, 48000, ss.AUTO_BLOCK))
        self.assertTrue(a["split"])

    def test_offset_parsing(self):
        self.assertEqual(ss.parse_offset_ms("8,2"), 8.2)
        self.assertEqual(ss.parse_offset_ms(" 0 "), 0.0)
        for bad in ("", "abc", "-1", "501", "nan"):
            self.assertIsNone(ss.parse_offset_ms(bad), bad)

    def test_ms_to_samples(self):
        self.assertEqual(ss.ms_to_samples(10.0, 48000), 480)
        self.assertEqual(ss.ms_to_samples(0, 48000), 0)


@unittest.skipIf(project_io is None, "project_io needs soundfile")
class ProjectAudioSectionTests(unittest.TestCase):
    def _save(self, e, name="p.llproj"):
        path = os.path.join(tempfile.mkdtemp(), name)
        project_io.save_project(path, e)
        return path

    def test_audio_section_round_trip(self):
        from tests.fake_stream import make_engine
        e = make_engine(44100, 128)
        _, tr = project_io.load_project(self._save(e))
        self.assertEqual(tr["audio"], {"sample_rate": 44100, "block_size": 128, "present": True})

    def test_old_file_gets_defaults(self):
        import zipfile
        from tests.fake_stream import make_engine
        path = self._save(make_engine(48000, 64))
        old = path + ".old"
        with zipfile.ZipFile(path) as zin, zipfile.ZipFile(old, "w") as zout:
            for n in zin.namelist():
                data = zin.read(n)
                if n == "project.json":
                    d = json.loads(data)
                    d.pop("audio")
                    data = json.dumps(d).encode()
                zout.writestr(n, data)
        _, tr = project_io.load_project(old)
        self.assertEqual(tr["audio"]["sample_rate"], 48000)
        self.assertEqual(tr["audio"]["block_size"], 64)
        self.assertFalse(tr["audio"]["present"])


def _tk_root():
    try:
        import tkinter as tk
        return tk.Tk()
    except Exception:
        return None


class PanelSmokeTests(unittest.TestCase):
    """Real Tk window: build the panel, change values, read them back."""

    def setUp(self):
        self.root = _tk_root()
        if self.root is None:
            self.skipTest("no Tk / display here (runs on the PC)")
        from audio_settings_panel import AudioSettingsPanel
        self.changes = 0
        self.p = AudioSettingsPanel(self.root, on_mount=lambda: None,
                                    on_change=self._count)
        self.p.set_devices(IN, OUT, ROWS)

    def tearDown(self):
        if self.root is not None:
            self.root.destroy()

    def _count(self):
        self.changes += 1

    def test_defaults_are_wasapi_exclusive(self):
        c = self.p.get_config()
        self.assertEqual((c.api, c.exclusive, c.sample_rate, c.block_size),
                         (WASAPI_NAME, True, 48000, ss.AUTO_BLOCK))
        self.assertTrue(c.split)
        self.assertEqual((c.in_device, c.out_device), (5, 7))

    def test_driver_switch_filters_and_disables_exclusive(self):
        self.p.driver_var.set("MME")
        self.p._driver_changed()
        c = self.p.get_config()
        self.assertFalse(c.exclusive)
        self.assertEqual((c.in_device, c.out_device), (1, 2))
        self.assertGreaterEqual(self.changes, 1)

    def test_auto_and_offset(self):
        self.p.driver_var.set("MME")
        self.p._driver_changed()
        self.p.block_var.set("256")
        self.p.apply_auto()
        c = self.p.get_config()
        self.assertEqual((c.api, c.exclusive, c.block_size), (WASAPI_NAME, True, ss.AUTO_BLOCK))
        self.assertTrue(c.split)
        self.p.offset_var.set("8.2")
        self.assertAlmostEqual(self.p.record_offset_ms(), 8.2)
        self.p.offset_var.set("junk")
        self.assertEqual(self.p.record_offset_ms(), 0.0)

    def test_settings_round_trip_through_panel(self):
        s = dict(ss.DEFAULT_SETTINGS, block_size=128, record_offset_ms=5.0, in_device="Line In")
        self.p.apply_settings(s)
        got = self.p.get_settings()
        self.assertEqual((got["block_size"], got["in_device"], got["record_offset_ms"]),
                         (128, "Line In", 5.0))


if __name__ == "__main__":
    unittest.main()
