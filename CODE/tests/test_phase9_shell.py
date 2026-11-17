"""Phase 9 / T010: tabbed app shell (top bar, Tracks / Mixer / Audio / Debug, full screen).
Builds LiveLooperApp under Xvfb with the sounddevice stub; skipped without Tk or a display."""
import os
import sys
import types
import unittest

from tests import _stubs  # noqa: F401

try:
    import tkinter as tk
    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class AppShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import settings_store
        cls._orig_load = settings_store.load_settings
        cls._orig_save = settings_store.save_settings
        # never touch the user's real settings.json from a test
        settings_store.save_settings = lambda *a, **k: None

    @classmethod
    def tearDownClass(cls):
        import settings_store
        settings_store.load_settings = cls._orig_load
        settings_store.save_settings = cls._orig_save

    def setUp(self):
        import ui_theme
        from app import LiveLooperApp
        ui_theme.set_scale(1.0)
        self.root = tk.Tk()
        self.app = LiveLooperApp(self.root)
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

    def _key(self, seq):
        self.root.focus_force()
        self.root.event_generate(seq)
        self._settle()

    # ------------------------------------------------------------------ tabs
    def test_notebook_tabs_in_order(self):
        nb = self.app.notebook
        titles = [nb.tab(t, "text").strip() for t in nb.tabs()]
        self.assertEqual(titles, ["Tracks", "Mixer", "Audio", "Debug", "Lab"])

    def test_ctrl_1_to_4_select_tabs(self):
        for i, name in enumerate(("tracks", "mixer", "audio", "debug")):
            self._key(f"<Control-Key-{i + 1}>")
            self.assertEqual(self.app.current_tab_name(), name)
            self.assertEqual(self.app.notebook.index(self.app.notebook.select()), i)

    def test_tab_contract_methods_exist(self):
        for name, tab in self.app.tab_widgets.items():
            self.assertTrue(tab.title)
            tab.on_show()
            tab.on_tick()

    def test_load_tab_uses_tab_module_when_present(self):
        import tabs
        mod = types.ModuleType("tab_mixer")

        class Tab(tabs.BaseTab):
            title = "Custom"
        mod.Tab = Tab
        sys.modules["tab_mixer"] = mod
        try:
            tab = tabs.load_tab("mixer", self.app.notebook, self.app)
            self.assertIsInstance(tab, Tab)
            tab.destroy()
        finally:
            del sys.modules["tab_mixer"]
        # no module tab_<name> -> the default class is used (T014 added a real tab_mixer, so the
        # fallback is checked with a name that has no module)
        tabs._DEFAULTS["scratch"] = tabs.MixerTab
        try:
            default = tabs.load_tab("scratch", self.app.notebook, self.app)
        finally:
            del tabs._DEFAULTS["scratch"]
        self.assertIsInstance(default, tabs.MixerTab)
        default.destroy()

    # --------------------------------------------------------------- top bar
    def test_top_bar_visible_on_every_tab(self):
        for name in ("tracks", "mixer", "audio", "debug"):
            self.app.select_tab(name)
            self._settle()
            for w in (self.app.top_bar, self.app.play_btn, self.app.rec_btn, self.app.time_lbl,
                      self.app.master_vol, self.app.status_lbl, self.app.in_meter):
                self.assertTrue(w.winfo_viewable(), f"{w} hidden on tab {name}")
            self.assertGreater(self.app.play_btn.winfo_width(), 20)

    def test_space_toggles_play_from_every_tab(self):
        calls = []
        self.app.toggle_play = lambda: calls.append(self.app.current_tab_name())
        self.app.play_btn.config(state="normal")
        for name in ("tracks", "mixer", "audio", "debug"):
            self.app.select_tab(name)
            self._settle()
            self._key("<space>")
        self.assertEqual(calls, ["tracks", "mixer", "audio", "debug"])

    def test_space_ignored_while_typing(self):
        calls = []
        self.app.toggle_play = lambda: calls.append(1)
        self.app.play_btn.config(state="normal")
        self.app.select_tab("debug")
        self._settle()
        ent = [w for w in self._walk(self.app.debug_center) if w.winfo_class() == "TEntry"][0]
        ent.focus_force()
        self._settle()
        ent.event_generate("<space>")
        self._settle()
        self.assertEqual(calls, [])

    def _walk(self, w):
        for c in w.winfo_children():
            yield c
            yield from self._walk(c)

    def test_f12_opens_debug_tab_and_test_bar(self):
        self._key("<F12>")
        self.assertEqual(self.app.current_tab_name(), "debug")
        self.assertTrue(self.app.debug_center.test_bar.winfo_manager())
        self._key("<F12>")
        self.assertFalse(self.app.debug_center.test_bar.winfo_manager())

    def test_time_readout(self):
        self.app._set_time(75.34)
        self.assertEqual(self.app.time_lbl.cget("text"), "01:15.3")
        self.app._set_time(-3)
        self.assertEqual(self.app.time_lbl.cget("text"), "00:00.0")

    # ------------------------------------------------------------ Tracks tab
    def test_add_empty_track_puts_strip_in_tracks_tab(self):
        tt = self.app.tracks_tab
        self.assertEqual(len(tt.track_strips), 0)
        self.app.add_empty_track()
        self._settle()
        self.assertEqual(len(tt.track_strips), 1)
        strip = next(iter(tt.track_strips.values()))
        self.assertTrue(str(strip.waveform).startswith(str(tt)))
        self.assertTrue(str(strip.header).startswith(str(tt)))
        self.assertEqual(self.app.track_count_lbl.cget("text"), "1 track")
        self.assertIs(self.app.view, tt.view)

    def test_remove_and_rebuild_tracks(self):
        for _ in range(3):
            self.app.add_empty_track()
        track = self.app.engine.tracks[1]
        self.app.remove_track(track)
        self.assertEqual(len(self.app.track_strips), 2)
        self.assertEqual(self.app.track_count_lbl.cget("text"), "2 tracks")
        self.app.rebuild_all_strips()
        self.assertEqual(len(self.app.track_strips), 2)
        self.app.engine.clear_all_tracks()
        self.app.rebuild_all_strips()
        self.assertEqual(len(self.app.track_strips), 0)
        self.assertTrue(self.app.tracks_tab.empty_state_lbl.winfo_manager())

    def test_three_tracks_fully_visible_at_1366x768(self):
        self.root.geometry("1366x768+0+0")
        for _ in range(3):
            self.app.add_empty_track()
        self.app.select_tab("tracks")
        self._settle(8)
        tt = self.app.tracks_tab
        view_h = tt.tracks_canvas.winfo_height()
        self.assertGreater(view_h, 0)
        strips = list(tt.track_strips.values())
        for s in strips:
            bottom = s.waveform.winfo_y() + s.waveform.winfo_height()
            self.assertLessEqual(bottom, view_h, "track row cut off")
            self.assertGreater(s.waveform.winfo_height(), 40)
        self.assertEqual(len(strips), 3)

    # --------------------------------------------------------------- Audio tab
    def test_audio_tab_holds_settings_and_options(self):
        at = self.app.tab_widgets["audio"]
        self.assertTrue(str(self.app.audio_panel).startswith(str(at)))
        self.assertTrue(str(self.app.load_graph).startswith(str(at)))
        self.assertIs(self.app.mount_btn, self.app.audio_panel.mount_btn)
        self.app.cleanup_var.set(False)
        self.app._on_cleanup_toggle()
        self.assertFalse(self.app.engine.input_cleanup_enabled)
        self.app.monitor_var.set(True)
        self.app._on_monitor_toggle()
        self.assertTrue(self.app.engine.input_monitor_enabled)

    def test_debug_tab_holds_debug_center(self):
        dt = self.app.tab_widgets["debug"]
        self.assertTrue(str(self.app.debug_center).startswith(str(dt)))
        self.assertIs(self.app.console, self.app.debug_center.console)
        self.app.log("shell test line", "INFO")
        self.app.debug_center.pump()
        self.assertIn("shell test line", self.app.console.get("1.0", "end"))

    # ----------------------------------------------------------------- window
    def test_window_title_unchanged(self):
        from version import APP_NAME, APP_VERSION
        self.assertEqual(self.root.title(), f"{APP_NAME} {APP_VERSION}")

    def test_window_starts_maximized(self):
        self.root.update()
        self.app._ensure_maximized()      # the 300 ms fallback, run now
        self._settle()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.assertTrue(self.app.is_maximized() or
                        (self.root.winfo_width() >= sw * 0.9 and self.root.winfo_height() >= sh * 0.8))

    def test_f11_toggles_full_screen(self):
        calls = []
        real = self.root.attributes
        # a bare Xvfb has no window manager, so record the request instead of reading it back
        self.root.attributes = lambda *a: calls.append(a) or real(*a)
        self.assertFalse(self.app.fullscreen)
        self._key("<F11>")
        self.assertTrue(self.app.fullscreen)
        self._key("<F11>")
        self.assertFalse(self.app.fullscreen)
        self.assertEqual(calls, [("-fullscreen", True), ("-fullscreen", False)])

    def test_menu_has_file_and_view(self):
        m = self.app.menubar
        labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1)]
        self.assertEqual(labels, ["File", "View"])
        filem = m.nametowidget(m.entrycget(0, "menu"))
        names = [filem.entrycget(i, "label") for i in range(filem.index("end") + 1)
                 if filem.type(i) == "command"]
        self.assertEqual(names, ["New project", "Open project...", "Save project...",
                                 "Import audio...", "Export mixdown...", "Quit"])

    def test_public_methods_keep_their_names(self):
        for name in ("toggle_play", "toggle_record", "rewind", "add_empty_track", "import_audio",
                     "save_project", "load_project", "new_project", "open_master_fx",
                     "calibrate_latency", "toggle_engine", "export_mix"):
            self.assertTrue(callable(getattr(self.app, name)), name)


if __name__ == "__main__":
    unittest.main()
