"""Phase 9 / T012: the Audio tab (tab_audio.Tab) and the restyled AudioSettingsPanel.
Builds LiveLooperApp under Xvfb with the sounddevice stub; skipped without Tk or a display."""
import unittest

from tests import _stubs  # noqa: F401

try:
    import tkinter as tk
    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


class _FakeTelemetry:
    xruns = 3
    overruns = 2

    def cpu_load(self):
        return 0.42

    def peak_load(self):
        return 0.8

    def history_loads(self):
        import numpy as np
        return np.linspace(0.1, 0.9, 100)


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class AudioTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import settings_store
        cls._orig_save = settings_store.save_settings
        settings_store.save_settings = lambda *a, **k: None

    @classmethod
    def tearDownClass(cls):
        import settings_store
        settings_store.save_settings = cls._orig_save

    def setUp(self):
        import ui_theme
        from app import LiveLooperApp
        ui_theme.set_scale(1.0)
        self.root = tk.Tk()
        self.app = LiveLooperApp(self.root)
        self.root.geometry("1366x768")
        self.app.cancel_timers()
        self.app.select_tab("audio")
        self.tab = self.app.tab_widgets["audio"]
        self._settle()

    def tearDown(self):
        try:
            self.app.cancel_timers()
            self.app.dlog.close()
        except Exception:
            pass
        self.root.destroy()

    def _settle(self, n=5):
        for _ in range(n):
            self.root.update_idletasks()
            self.root.update()

    def test_audio_tab_is_the_new_class(self):
        import tab_audio
        self.assertIsInstance(self.tab, tab_audio.Tab)
        self.assertIs(self.app.audio_panel, self.tab.panel)
        self.assertIs(self.app.mount_btn, self.tab.panel.mount_btn)
        self.assertIs(self.app.load_graph, self.tab.load_graph)

    def test_has_the_four_sections(self):
        self.assertEqual(set(self.tab.sections), {"devices", "calibration", "monitoring", "status"})
        for name, w in self.tab.sections.items():
            self.assertTrue(w.winfo_viewable(), name)
            self.assertGreater(w.winfo_width(), 50, name)

    def test_monitoring_checks_use_app_variables(self):
        for attr in ("monitor_var", "rec_output_var", "cleanup_var"):
            cb = self.tab.option_checks[attr]
            before = getattr(self.app, attr).get()
            cb.invoke()
            self.assertNotEqual(getattr(self.app, attr).get(), before)
        self.assertEqual(self.app.engine.input_cleanup_enabled, self.app.cleanup_var.get())
        self.assertEqual(self.app.engine.input_monitor_enabled, self.app.monitor_var.get())
        self.assertEqual(self.app.engine.record_with_output_enabled, self.app.rec_output_var.get())

    def test_status_when_not_mounted(self):
        self.app.engine.is_active = False
        self.tab.on_tick()
        self.assertEqual(self.tab.stat_vars["mode"].get(), "not mounted")
        self.assertEqual(self.tab.stat_vars["cpu"].get(), "-")

    def test_status_with_fake_telemetry(self):
        eng = self.app.engine
        eng.is_active = True
        eng.telemetry = _FakeTelemetry()
        eng.peak_l, eng.peak_r, eng.input_peak = 0.5, 0.3, 0.25
        try:
            self.tab.on_tick()
            v = {k: s.get() for k, s in self.tab.stat_vars.items()}
            self.assertIn("42%", v["cpu"])
            self.assertIn("3 card", v["dropouts"])
            self.assertIn("2 late", v["dropouts"])
            self.assertNotEqual(v["rtt"], "-")
            self.assertNotEqual(v["mode"], "not mounted")
            self.assertTrue(self.tab.big_in_meter.find_all())
            self.app._draw_load_graph(eng.telemetry)       # reads the tab's canvas options
            self.assertGreater(len(self.tab.load_graph.find_all()), 10)
        finally:
            eng.is_active = False

    def test_status_updates_from_app_tick(self):
        calls = []
        orig = self.tab.refresh_status
        self.tab.refresh_status = lambda: calls.append(1) or orig()
        self.app.update_telemetry()
        self.app.cancel_timers()
        self.assertTrue(calls)

    def test_calibration_button_states(self):
        panel = self.app.audio_panel
        self.assertEqual(str(panel.calib_btn["state"]), "disabled")
        panel.set_mounted(True)
        self.assertEqual(str(panel.calib_btn["state"]), "normal")
        self.assertEqual(panel.mount_btn["text"], "UNMOUNT AUDIO ENGINE")
        panel.set_mounted(False)
        self.assertEqual(str(panel.calib_btn["state"]), "disabled")
        self.assertEqual(panel.mount_btn["text"], "MOUNT AUDIO ENGINE")
        panel.set_calibration({"rtt_ms": 12.3, "key": "k"})
        self.assertIn("12.3", panel.calib_lbl["text"])
        panel.set_calibration(None)
        self.assertIn("not calibrated", panel.calib_lbl["text"])

    def test_panel_public_names_still_exist(self):
        panel = self.app.audio_panel
        for name in ("get_settings", "apply_settings", "get_config", "set_devices", "set_mounted",
                     "set_calibration", "set_rate_block", "set_rate_locked",
                     "set_offset_ms", "record_offset_ms", "calib_btn", "calib_lbl", "mount_btn"):
            self.assertTrue(hasattr(panel, name), name)
        self.assertEqual(set(panel.get_settings()),
                         {"driver", "exclusive", "split", "sample_rate", "block_size", "record_offset_ms",
                          "in_device", "out_device", "calibration"})

    def test_panel_buttons_use_the_theme(self):
        buttons = [w for w in _walk(self.tab) if w.winfo_class() == "TButton"]
        self.assertTrue(buttons)
        for b in buttons:
            self.assertTrue(str(b.cget("style")).endswith(("Neutral.TButton", "Action.TButton",
                                                           "Stop.TButton")), str(b))

    def test_fits_at_1366x768(self):
        self._settle()
        for name, w in self.tab.sections.items():
            self.assertLessEqual(w.winfo_rootx() + w.winfo_width(), self.root.winfo_rootx() + 1366, name)


if __name__ == "__main__":
    unittest.main()
