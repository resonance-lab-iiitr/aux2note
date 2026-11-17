"""Phase 9 / T016: UI scale 80-200 percent everywhere (Ctrl +, Ctrl -, Ctrl 0, View menu).
The settings tests need no Tk; the rest builds LiveLooperApp under Xvfb with the sounddevice
stub and is skipped without Tk or a display."""
import json
import os
import tempfile
import unittest

import numpy as np

from tests import _stubs  # noqa: F401

try:
    import tkinter as tk
    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:
    HAVE_TK = False


# ---------------------------------------------------------------------- settings (no Tk)
class UiScaleSettingsTests(unittest.TestCase):
    def test_default_is_100_percent(self):
        import settings_store
        self.assertEqual(settings_store.DEFAULT_SETTINGS["ui_scale"], 1.0)
        self.assertEqual(settings_store.sanitize({})["ui_scale"], 1.0)
        self.assertEqual(settings_store.sanitize(None)["ui_scale"], 1.0)

    def test_valid_values_are_kept(self):
        import settings_store
        for v in (0.8, 1.0, 1.25, 1.5, 2.0, 1):
            self.assertAlmostEqual(settings_store.sanitize({"ui_scale": v})["ui_scale"], float(v))

    def test_invalid_values_fall_back_to_default(self):
        import settings_store
        for bad in (0.5, 0.79, 2.01, 5, -1, 0, "1.5", None, True, False, [1.5], float("nan"),
                    float("inf")):
            self.assertEqual(settings_store.sanitize({"ui_scale": bad})["ui_scale"], 1.0, bad)

    def test_round_trip_through_settings_json(self):
        import settings_store
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            data = dict(settings_store.DEFAULT_SETTINGS, ui_scale=1.4)
            self.assertTrue(settings_store.save_settings(data, path))
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["ui_scale"], 1.4)
            self.assertEqual(settings_store.load_settings(path)["ui_scale"], 1.4)

    def test_old_settings_file_without_ui_scale_loads_at_100_percent(self):
        import settings_store
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"driver": settings_store.DEFAULT_SETTINGS["driver"], "block_size": 256}, f)
            loaded = settings_store.load_settings(path)
            self.assertEqual(loaded["ui_scale"], 1.0)
            self.assertEqual(loaded["block_size"], 256)

    def test_ui_theme_range_matches_settings_range(self):
        import settings_store
        import ui_theme
        self.assertEqual((ui_theme.SCALE_MIN, ui_theme.SCALE_MAX),
                         (settings_store.UI_SCALE_MIN, settings_store.UI_SCALE_MAX))


# ---------------------------------------------------------------------- waveform helpers (no app)
@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class ScaleHelperTests(unittest.TestCase):
    def tearDown(self):
        import ui_theme
        ui_theme.set_scale(1.0)

    def test_snap_distance_and_fonts_follow_the_scale(self):
        import ui_theme
        import waveform_widget as ww
        ui_theme.set_scale(1.0)
        self.assertAlmostEqual(ww.snap_px(), ww.SNAP_PX)
        self.assertEqual(ww._font("Consolas", 9, "bold"), ("Consolas", 9, "bold"))
        self.assertEqual(ww._font("Segoe UI", 8), ("Segoe UI", 8))
        ui_theme.set_scale(1.5)
        self.assertAlmostEqual(ww.snap_px(), ww.SNAP_PX * 1.5)
        self.assertGreater(ww._font("Consolas", 9, "bold")[1], 9)
        self.assertEqual(ww.control_col_width(), round(ww.CONTROL_COL_WIDTH * 1.5))
        self.assertEqual(ww.row_height(object()), round(ww.TRACK_ROW_HEIGHT * 1.5))
        ui_theme.set_scale(0.8)
        self.assertLess(ww.snap_px(), ww.SNAP_PX)
        self.assertLess(ww.control_col_width(), ww.CONTROL_COL_WIDTH)

    def test_row_height_keeps_the_level_numbers_in_the_model(self):
        import ui_theme
        import waveform_widget as ww
        from timeline_view import TimelineView
        view = TimelineView()
        ui_theme.set_scale(1.0)
        base = ww.row_height(view)
        self.assertEqual(base, view.track_height)
        ui_theme.set_scale(2.0)
        self.assertEqual(view.track_height, base)          # the model still holds 48/72/96/140/200
        self.assertEqual(ww.row_height(view), base * 2)


# ---------------------------------------------------------------------- whole app
@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class UiScaleAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import settings_store
        cls._orig_save = settings_store.save_settings
        cls._orig_load = settings_store.load_settings
        cls.saved = []
        settings_store.save_settings = lambda data, *a, **k: cls.saved.append(dict(data)) or True

    @classmethod
    def tearDownClass(cls):
        import settings_store
        settings_store.save_settings = cls._orig_save
        settings_store.load_settings = cls._orig_load

    def setUp(self):
        import ui_theme
        from app import LiveLooperApp
        self.theme = ui_theme
        ui_theme.set_scale(1.0)
        self.saved.clear()
        self.root = tk.Tk()
        self.app = LiveLooperApp(self.root)
        self.app.cancel_timers()
        self.root.geometry("1366x768+0+0")
        self.sr = self.app.engine.sample_rate
        self._settle()

    def tearDown(self):
        try:
            self.app.cancel_timers()
            self.app.dlog.close()
        except Exception:
            pass
        self.root.destroy()
        self.theme.set_scale(1.0)

    def _settle(self, n=6):
        for _ in range(n):
            self.root.update_idletasks()
            self.root.update()

    def _key(self, seq):
        self.root.focus_force()
        self.root.event_generate(seq)
        self._settle()

    def _tracks(self, n=3):
        for i in range(n):
            self.app.add_empty_track()
            t = self.app.engine.tracks[-1]
            t.buffer = np.full(int(self.sr * (3 + i)), 0.3, dtype=np.float32)
            t.peaks_cache = None
            t.offset = int(self.sr * i)
        self.app.tracks_tab.redraw_all()
        self._settle()
        return self.app.engine.tracks

    def _measure(self):
        """Pixel sizes of one widget per tab at the current scale."""
        app = self.app
        out = {}
        app.select_tab("tracks")
        self._settle()
        tt = app.tracks_tab
        strip = next(iter(tt.track_strips.values()))
        out["toolbar_h"] = tt.toolbar.winfo_reqheight()
        out["header_w"] = strip.header._col.winfo_width()
        out["header_h"] = strip.header._col.winfo_height()
        out["ruler_h"] = tt.ruler.winfo_height()
        app.select_tab("mixer")
        self._settle()
        mixer = app.tab_widgets["mixer"]
        out["strip_w"] = next(iter(mixer.strips.values())).winfo_reqwidth()
        out["master_w"] = mixer.master_strip.winfo_reqwidth()
        app.select_tab("audio")
        self._settle()
        out["load_w"] = app.load_graph.winfo_width()
        out["load_h"] = app.load_graph.winfo_height()
        app.select_tab("debug")
        self._settle()
        out["debug_load_h"] = app.debug_center.load_canvas.winfo_reqheight()
        out["top_meter_w"] = app.in_meter.winfo_width()
        return out

    # ------------------------------------------------------------------ keys / menu
    def test_ctrl_plus_minus_zero_change_the_scale_in_10_percent_steps(self):
        self.assertAlmostEqual(self.theme.get_scale(), 1.0)
        self._key("<Control-plus>")
        self.assertAlmostEqual(self.theme.get_scale(), 1.1)
        self._key("<Control-equal>")
        self.assertAlmostEqual(self.theme.get_scale(), 1.2)
        self._key("<Control-KP_Add>")
        self.assertAlmostEqual(self.theme.get_scale(), 1.3)
        self._key("<Control-minus>")
        self.assertAlmostEqual(self.theme.get_scale(), 1.2)
        self._key("<Control-KP_Subtract>")
        self.assertAlmostEqual(self.theme.get_scale(), 1.1)
        self._key("<Control-Key-0>")
        self.assertAlmostEqual(self.theme.get_scale(), 1.0)

    def test_scale_stops_at_the_limits(self):
        for _ in range(15):
            self.app.change_ui_scale(+0.1)
        self.assertAlmostEqual(self.theme.get_scale(), 2.0)
        self.app.change_ui_scale(+0.1)
        self.assertAlmostEqual(self.theme.get_scale(), 2.0)
        for _ in range(20):
            self.app.change_ui_scale(-0.1)
        self.assertAlmostEqual(self.theme.get_scale(), 0.8)
        self.app.change_ui_scale(None)
        self.assertAlmostEqual(self.theme.get_scale(), 1.0)

    def test_view_menu_has_scale_entries_and_keeps_timeline_zoom(self):
        viewm = self.app.menubar.nametowidget(self.app.menubar.entrycget(
            self.app.menubar.index("View"), "menu"))
        by_label = {viewm.entrycget(i, "label"): i for i in range(viewm.index("end") + 1)
                    if viewm.type(i) == "command"}
        for want in ("Timeline zoom in", "Timeline zoom out", "UI scale larger",
                     "UI scale smaller", "UI scale reset (100%)"):
            self.assertIn(want, by_label)
        viewm.invoke(by_label["UI scale larger"])
        self.assertAlmostEqual(self.theme.get_scale(), 1.1)
        viewm.invoke(by_label["UI scale smaller"])
        viewm.invoke(by_label["UI scale smaller"])
        self.assertAlmostEqual(self.theme.get_scale(), 0.9)
        viewm.invoke(by_label["UI scale reset (100%)"])
        self.assertAlmostEqual(self.theme.get_scale(), 1.0)

    def test_ctrl_wheel_in_the_tracks_tab_still_zooms_the_timeline_not_the_ui(self):
        self._tracks(1)
        self.app.select_tab("tracks")
        self._settle()
        view = self.app.tracks_tab.view
        before = view.px_per_sec
        self.app.tracks_tab._on_wheel(+1, type("E", (), {"state": 0x4, "x_root": 400, "y_root": 300})())
        self.assertNotEqual(view.px_per_sec, before)
        self.assertAlmostEqual(self.theme.get_scale(), 1.0)

    # ------------------------------------------------------------------ settings
    def test_changing_the_scale_saves_it_and_audio_settings_keep_it(self):
        self.app.change_ui_scale(+0.1)
        self.assertTrue(self.saved)
        self.assertAlmostEqual(self.saved[-1]["ui_scale"], 1.1)
        self.saved.clear()
        self.app._on_settings_changed()           # the audio panel does not know ui_scale
        self.assertAlmostEqual(self.saved[-1]["ui_scale"], 1.1)

    def test_scale_is_restored_from_settings_before_the_tabs_are_built(self):
        import settings_store
        from app import LiveLooperApp
        self.app.cancel_timers()
        self.root.destroy()
        self.theme.set_scale(1.0)
        settings_store.load_settings = lambda *a, **k: dict(settings_store.DEFAULT_SETTINGS,
                                                            ui_scale=1.5)
        self.root = tk.Tk()
        try:
            self.app = LiveLooperApp(self.root)
            self.app.cancel_timers()
            self.root.geometry("1366x768+0+0")
            self._settle()
            self.assertAlmostEqual(self.theme.get_scale(), 1.5)
            mixer_btn = self.app.tab_widgets["mixer"].master_strip
            self.assertGreaterEqual(int(self.app.load_graph["width"]), self.theme.scaled(300))
            self.assertEqual(int(self.app.load_graph["width"]), round(300 * 1.5))
            self.assertIsNotNone(mixer_btn)
        finally:
            settings_store.load_settings = self._orig_load

    # ------------------------------------------------------------------ sizes
    def test_sizes_grow_at_150_shrink_at_80_and_return_exactly_at_100(self):
        self._tracks(3)
        first = self._measure()
        self.theme.set_scale(1.5)
        self._settle()
        big = self._measure()
        for key in ("toolbar_h", "header_w", "header_h", "ruler_h", "strip_w", "master_w",
                    "load_w", "load_h", "debug_load_h", "top_meter_w"):
            self.assertGreater(big[key], first[key], f"{key}: {big[key]} !> {first[key]}")
        self.theme.set_scale(0.8)
        self._settle()
        small = self._measure()
        for key in ("header_w", "header_h", "ruler_h", "strip_w", "master_w", "load_w",
                    "load_h", "debug_load_h", "top_meter_w"):
            self.assertLess(small[key], first[key], f"{key}: {small[key]} !< {first[key]}")
        self.theme.set_scale(1.0)
        self._settle()
        again = self._measure()
        self.assertEqual(again, first)

    def test_track_rows_follow_level_times_scale(self):
        self._tracks(2)
        tt = self.app.tracks_tab
        level = tt.view.track_height
        self.theme.set_scale(1.5)
        self._settle()
        for strip in tt.track_strips.values():
            self.assertEqual(strip.waveform.winfo_height(), round(level * 1.5))
            self.assertEqual(strip.header._col.winfo_height(), round(level * 1.5))
        self.assertEqual(tt.view.track_height, level)

    def test_header_widgets_stay_inside_the_header_column_at_every_scale(self):
        self._tracks(1)
        tt = self.app.tracks_tab
        strip = next(iter(tt.track_strips.values()))
        for sc in (0.8, 1.0, 1.5, 2.0):
            self.theme.set_scale(sc)
            self._settle()
            col_w = strip.header._col.winfo_width()
            for widget, _kw in strip.header._always + strip.header._row2:
                if widget.winfo_manager():
                    self.assertLessEqual(widget.winfo_x() + widget.winfo_width(), col_w + 1,
                                         f"scale {sc}: {widget}")

    def test_readout_font_and_snap_distance_follow_the_scale(self):
        import waveform_widget as ww
        tracks = self._tracks(2)
        wf = self.app.tracks_tab.track_strips[tracks[0].id].waveform
        wf._readout = "+0.100 s  (100 ms)"
        wf.redraw()
        first = [wf.itemcget(i, "font") for i in wf.find_withtag("readout") if wf.type(i) == "text"]
        self.assertTrue(first)
        self.theme.set_scale(1.5)
        self._settle()
        wf._readout = "+0.100 s  (100 ms)"
        wf.redraw()
        big = [wf.itemcget(i, "font") for i in wf.find_withtag("readout") if wf.type(i) == "text"]
        self.assertTrue(big)
        self.assertNotEqual(first[0], big[0])
        self.assertIn(str(ww._font("Consolas", 9, "bold")[1]), big[0])
        self.assertAlmostEqual(ww.snap_px(), ww.SNAP_PX * 1.5)
        wf._readout = None
        self.theme.set_scale(1.0)
        self._settle()
        self.assertAlmostEqual(ww.snap_px(), ww.SNAP_PX)

    # ------------------------------------------------------------------ mixer state
    def test_mixer_strips_are_rebuilt_and_keep_their_state(self):
        tracks = self._tracks(3)
        tracks[0].gain, tracks[0].pan, tracks[0].mute = 1.35, -0.5, True
        tracks[1].solo = True
        tracks[2].effects.reverb.enabled = True
        self.app.engine.master_gain = 0.7
        mixer = self.app.tab_widgets["mixer"]
        mixer.on_show()
        self._settle()
        old_strips = dict(mixer.strips)
        old_master = mixer.master_strip
        self.theme.set_scale(1.5)
        self._settle()
        self.assertIsNot(mixer.master_strip, old_master)
        self.assertEqual(set(mixer.strips), set(old_strips))
        for tid, strip in mixer.strips.items():
            self.assertIsNot(strip, old_strips[tid])
        s0, s1, s2 = (mixer.strips[t.id] for t in tracks)
        self.assertAlmostEqual(s0.vol_scale.get(), 1.35, places=2)
        self.assertAlmostEqual(s0.pan_scale.get(), -0.5, places=2)
        self.assertTrue(s0.mute_var.get())
        self.assertTrue(s1.solo_var.get())
        self.assertTrue(s2.rack.vars["reverb"].get())
        self.assertAlmostEqual(mixer.master_strip.vol_scale.get(), 0.7, places=2)
        # the new fader and meter are longer
        self.assertEqual(int(s0.vol_scale.cget("length")), round(176 * 1.5))
        self.assertEqual(int(s0.meter.canvas["height"]), round(176 * 1.5))
        # still wired to the model
        s0.vol_scale.set(0.5)
        self._settle()                      # Tk runs a Scale's command at idle time
        self.assertAlmostEqual(tracks[0].gain, 0.5, places=2)

    def test_empty_mixer_survives_a_scale_change(self):
        mixer = self.app.tab_widgets["mixer"]
        self.theme.set_scale(1.3)
        self._settle()
        self.assertEqual(mixer.strips, {})
        self.assertTrue(mixer.empty_lbl.winfo_manager())

    def test_top_bar_buttons_stay_on_screen_at_150_percent(self):
        self.theme.set_scale(1.5)
        self._settle()
        self.assertEqual(str(self.app.top_right.master), str(self.app.top_bar))
        self.assertTrue(self.app.top_row_wrap.winfo_manager())
        right = self.app.top_right.winfo_rootx() + self.app.top_right.winfo_width()
        self.assertLessEqual(right, self.root.winfo_rootx() + self.root.winfo_width())
        self.theme.set_scale(1.0)
        self._settle()
        self.assertFalse(self.app.top_row_wrap.winfo_manager())

    # ------------------------------------------------------------------ misc
    def test_debug_tab_columns_and_sub_tab_order_survive(self):
        dc = self.app.debug_center
        order = [dc.nb.tab(t, "text").strip() for t in dc.nb.tabs()]
        self.assertEqual(order, ["Log", "Engine", "Devices", "Tracks", "Load", "Report"])
        tv = dc.dev_tree
        w1 = tv.column("Name", "width")
        self.theme.set_scale(1.5)
        self._settle()
        self.assertGreater(tv.column("Name", "width"), w1)
        self.theme.set_scale(1.0)
        self._settle()
        self.assertEqual(tv.column("Name", "width"), w1)
        order2 = [dc.nb.tab(t, "text").strip() for t in dc.nb.tabs()]
        self.assertEqual(order2, order)

    def test_on_close_removes_the_app_listener(self):
        self.assertIn(self.app._on_ui_scale, self.theme._listeners)
        self.app.cancel_timers()
        # on_close destroys the root: replace the engine / log calls with no-ops first
        self.app.engine.close_stream = lambda: None
        self.app.dlog.close = lambda: None
        self.app.on_close()
        self.assertNotIn(self.app._on_ui_scale, self.theme._listeners)
        self.root = tk.Tk()          # tearDown destroys self.root


if __name__ == "__main__":
    unittest.main()
