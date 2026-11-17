"""Phase 9 / T011: the Tracks tab workspace (tab_tracks.Tab) and the viewport drawing mode of
waveform_widget. Builds LiveLooperApp under Xvfb with the sounddevice stub; Tk tests are skipped
without a display."""
import re
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


class VisiblePeaksTests(unittest.TestCase):
    """visible_peaks needs no Tk."""

    def test_matches_naive_min_max_per_column(self):
        from waveform_widget import visible_peaks
        rng = np.random.default_rng(1)
        buf = rng.uniform(-1, 1, 10_000).astype(np.float32)
        spp = 37.5
        mins, maxs = visible_peaks(buf, 20, 60, spp)
        self.assertEqual(len(mins), 40)
        for k, col in enumerate(range(20, 60)):
            a, b = int(np.floor(col * spp)), int(np.floor((col + 1) * spp))
            self.assertAlmostEqual(float(mins[k]), float(buf[a:b].min()), places=6)
            self.assertAlmostEqual(float(maxs[k]), float(buf[a:b].max()), places=6)

    def test_columns_past_the_end_and_empty_input(self):
        from waveform_widget import visible_peaks
        buf = np.ones(100, dtype=np.float32)
        mins, maxs = visible_peaks(buf, 0, 10, 50.0)       # only 2 columns hold samples
        self.assertEqual(len(mins), 10)
        self.assertTrue(np.all(maxs[:2] == 1.0))
        mins, maxs = visible_peaks(np.zeros(0, dtype=np.float32), 0, 5, 10.0)
        self.assertEqual(len(mins), 5)
        mins, maxs = visible_peaks(buf, 5, 5, 10.0)
        self.assertEqual(len(mins), 0)


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class TracksTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import settings_store
        cls._orig_save = settings_store.save_settings
        settings_store.save_settings = lambda *a, **k: None    # never touch the real settings.json

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
        self.app.cancel_timers()                    # no 60 ms playhead tick: the tests drive set_playhead
        self.root.geometry("1366x768+0+0")          # after the app: it sets its own size
        self.tab = self.app.tracks_tab
        self._settle()
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), (1366, 768))

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

    def _tracks(self, n=3, seconds=(8, 11, 14), offsets=(0.0, 1.5, 3.0), noise=True):
        sr = self.app.engine.sample_rate
        rng = np.random.default_rng(7)
        for i in range(n):
            self.app.add_empty_track()
            t = self.app.engine.tracks[-1]
            count = int(sr * seconds[i % len(seconds)])
            t.buffer = (rng.uniform(-0.8, 0.8, count) if noise else np.zeros(count)).astype(np.float32)
            t.peaks_cache = None
            t.offset = int(sr * offsets[i % len(offsets)])
        self.tab.redraw_all()
        self._settle()
        return self.app.engine.tracks

    def _wheel(self, widget, x, delta, state_event="<Control-MouseWheel>"):
        widget.event_generate(state_event, x=x, y=10, delta=delta)
        self._settle()

    # ------------------------------------------------------------ loading
    def test_tab_module_is_used_and_view_is_new_model(self):
        import tab_tracks
        import timeline_view
        self.assertIsInstance(self.tab, tab_tracks.Tab)
        self.assertIsInstance(self.tab.view, timeline_view.TimelineView)
        self.assertIs(self.app.view, self.tab.view)
        self.assertTrue(self.tab.ruler.virtual)

    def test_public_interface_kept(self):
        for name in ("add_track_strip", "remove_track_strip", "rebuild_all", "refresh_states",
                     "redraw_all", "set_playhead", "redraw_recording", "on_show", "on_tick"):
            self.assertTrue(callable(getattr(self.tab, name)), name)
        for name in ("view", "ruler", "track_strips", "empty_state_lbl"):
            self.assertTrue(hasattr(self.tab, name), name)

    # ----------------------------------------------------------- add track
    def _button(self, text):
        def walk(w):
            for c in w.winfo_children():
                yield c
                yield from walk(c)
        for w in walk(self.tab.toolbar):
            if w.winfo_class() == "TButton" and str(w.cget("text")) == text:
                return w
        self.fail(f"no toolbar button {text!r}")

    def test_add_track_button_in_tab_adds_a_strip(self):
        self.assertEqual(len(self.tab.track_strips), 0)
        self._button("+ TRACK").invoke()
        self._settle()
        self.assertEqual(len(self.tab.track_strips), 1)
        self.assertEqual(len(self.app.engine.tracks), 1)
        self.assertFalse(self.tab.empty_state_lbl.winfo_ismapped())

    def test_remove_and_rebuild_keep_strips_in_sync(self):
        tracks = self._tracks(3)
        self.app.remove_track(tracks[1])
        self._settle()
        self.assertEqual(len(self.tab.track_strips), 2)
        self.app.rebuild_all_strips()
        self._settle()
        self.assertEqual([s.track for s in self.tab.track_strips.values()], list(self.app.engine.tracks))
        self.app.engine.clear_all_tracks()
        self.app.rebuild_all_strips()
        self._settle()
        self.assertEqual(len(self.tab.track_strips), 0)
        self.assertTrue(self.tab.empty_state_lbl.winfo_ismapped())

    # ----------------------------------------------------------------- zoom
    def test_ctrl_wheel_zoom_keeps_time_under_pointer(self):
        self._tracks(3)
        tab, view = self.tab, self.tab.view
        tab.scroll_to_px(300.0)
        self._settle()
        waveform = list(tab.track_strips.values())[0].waveform
        pointer_x = 400                                    # window pixel under the pointer
        sec_before = view.px_to_sec(tab.scroll_px + pointer_x)
        pps_before = view.px_per_sec
        self._wheel(waveform, pointer_x, 120)
        self.assertGreater(view.px_per_sec, pps_before)
        sec_after = view.px_to_sec(tab.scroll_px + pointer_x)
        self.assertLess(abs(sec_after - sec_before) * view.px_per_sec, 1.0)   # moves less than 1 px
        self._wheel(waveform, pointer_x, -120)
        self.assertAlmostEqual(view.px_per_sec, pps_before, places=6)

    def test_ctrl_wheel_zoom_works_on_the_ruler_and_empty_area(self):
        self._tracks(1)
        pps = self.tab.view.px_per_sec
        self._wheel(self.tab.ruler, 200, 120)
        self.assertGreater(self.tab.view.px_per_sec, pps)
        self._wheel(self.tab.tracks_canvas, 200, -120)
        self.assertAlmostEqual(self.tab.view.px_per_sec, pps, places=6)

    def test_view_menu_zoom_and_buttons(self):
        view = self.app.view
        pps = view.px_per_sec
        centre = self.tab.viewport_px() / 2
        sec_before = view.px_to_sec(self.tab.scroll_px + centre)
        view.zoom(1.25)                                    # what the View menu calls
        self._settle()
        self.assertAlmostEqual(view.px_per_sec, pps * 1.25, places=6)
        self.assertLess(abs(view.px_to_sec(self.tab.scroll_px + centre) - sec_before) * view.px_per_sec, 1.0)
        self._button("ZOOM -").invoke()
        self.assertAlmostEqual(view.px_per_sec, pps, places=6)
        self._button("ZOOM +").invoke()
        self.assertGreater(view.px_per_sec, pps)

    def test_zoom_limits_hold(self):
        view = self.tab.view
        for _ in range(60):
            self.tab.zoom_about(1.25, 100)
        self.assertEqual(view.px_per_sec, view.MAX_PX_PER_SEC)
        for _ in range(120):
            self.tab.zoom_about(0.8, 100)
        self.assertEqual(view.px_per_sec, view.MIN_PX_PER_SEC)
        self.assertEqual(self.tab.scroll_px, 0.0)

    def test_fit_shows_whole_clip_range(self):
        self._tracks(3)                                    # clips end at 8, 12.5 and 17 s
        tab, view = self.tab, self.tab.view
        total = tab.clip_range_sec()
        self.assertAlmostEqual(total, 17.0, places=2)
        view.set_px_per_sec(400)                           # zoomed far in, then scrolled
        tab.scroll_to_px(2000)
        self._button("FIT").invoke()
        self._settle()
        start, end = view.visible_range(tab.scroll_px, tab.viewport_px())
        self.assertEqual(tab.scroll_px, 0.0)
        self.assertLessEqual(start, 0.0)
        self.assertGreaterEqual(end, total)
        self.assertLess(end, total * 1.3)                  # not zoomed out much further than needed

    def test_fit_with_no_audio_keeps_zoom(self):
        pps = self.tab.view.px_per_sec
        self._button("FIT").invoke()
        self.assertEqual(self.tab.view.px_per_sec, pps)

    # ------------------------------------------------------------ row heights
    def test_row_height_buttons_resize_every_strip(self):
        self._tracks(3)
        view = self.tab.view
        sizes = []
        for _ in range(2):
            self._button("ROWS +").invoke()
            self._settle()
            sizes.append(view.track_height)
            for strip in self.tab.track_strips.values():
                self.assertEqual(strip.waveform.winfo_height(), view.track_height)
                self.assertEqual(strip.header.winfo_height(), view.track_height)
        self.assertEqual(sizes, [140, 200])
        for _ in range(4):
            self._button("ROWS -").invoke()
        self._settle()
        self.assertEqual(view.track_height, 48)
        for strip in self.tab.track_strips.values():
            self.assertEqual(strip.waveform.winfo_height(), 48)
            self.assertEqual(strip.header.winfo_height(), 48)

    def test_low_rows_hide_the_slider_rows_and_tall_rows_show_them(self):
        self._tracks(1)
        header = list(self.tab.track_strips.values())[0].header
        self.tab.view.set_height_level(0)
        self._settle()
        self.assertFalse(header.vol_scale.winfo_ismapped())
        self.assertFalse(header.fx_btn.winfo_ismapped())
        self.assertTrue(header.arm_chk.winfo_ismapped())
        self.tab.view.set_height_level(3)
        self._settle()
        self.assertTrue(header.vol_scale.winfo_ismapped())
        self.assertTrue(header.fx_btn.winfo_ismapped())

    def test_three_rows_fully_visible_at_1366x768(self):
        self._tracks(3)
        canvas = self.tab.tracks_canvas
        self.assertGreaterEqual(canvas.winfo_height(), 3 * (self.tab.view.track_height + 4))
        top = canvas.winfo_rooty()
        bottom = top + canvas.winfo_height()
        visible = 0
        for strip in self.tab.track_strips.values():
            y0 = strip.waveform.winfo_rooty()
            if y0 >= top and y0 + strip.waveform.winfo_height() <= bottom:
                visible += 1
            hy0 = strip.header.winfo_rooty()
            self.assertEqual(hy0, y0, "header and waveform rows must line up")
        self.assertGreaterEqual(visible, 3)

    def test_vertical_wheel_scrolls_headers_and_waveforms_together(self):
        self._tracks(3)
        for _ in range(4):
            self._button("ROWS +").invoke()                # 200 px rows: 3 tracks need scrolling
        self._settle()
        tab = self.tab
        self.assertEqual(tab.tracks_canvas.yview()[0], 0.0)
        waveform = list(tab.track_strips.values())[0].waveform
        self._wheel(waveform, 50, -120, "<MouseWheel>")
        self.assertGreater(tab.tracks_canvas.yview()[0], 0.0)
        self.assertEqual(tab.tracks_canvas.yview(), tab.header_canvas.yview())

    # --------------------------------------------------- horizontal scroll / ruler
    def test_ruler_follows_horizontal_scrolling(self):
        self._tracks(3)
        tab, ruler, view = self.tab, self.tab.ruler, self.tab.view
        for px in (0.0, 123.0, 900.0, 2500.0):
            tab.scroll_to_px(px)
            self._settle()
            self.assertEqual(ruler.scroll_px, tab.scroll_px)
            for strip in tab.track_strips.values():
                self.assertEqual(strip.waveform.scroll_px, tab.scroll_px)
            self.assertAlmostEqual(ruler.x_to_seconds(0), view.px_to_sec(tab.scroll_px), places=6)
        # the scrollbar drives the same thing
        tab._on_hscroll("moveto", "0.1")
        self.assertAlmostEqual(tab.scroll_px, 0.1 * tab.content_width_px(), places=3)
        self.assertEqual(ruler.scroll_px, tab.scroll_px)

    def test_ruler_labels_are_readable_and_cover_the_window(self):
        self._tracks(2)
        tab, ruler, view = self.tab, self.tab.ruler, self.tab.view
        for pps, scroll in ((80.0, 0.0), (400.0, 1500.0), (10.0, 0.0), (1500.0, 3000.0)):
            view.set_px_per_sec(pps)
            tab.scroll_to_px(scroll, force=True)
            self._settle()
            labels = [ruler.itemcget(i, "text") for i in ruler.find_withtag("label")]
            self.assertTrue(labels)
            for text in labels:
                self.assertRegex(text, r"^(\d+:)?\d{1,2}:\d{2}(\.\d{1,2})?$|^\d+:\d{2}(\.\d{1,2})?$")
            # at least one label for every ~tick spacing across the window, none closer than 60 px
            xs = sorted(ruler.coords(i)[0] for i in ruler.find_withtag("label"))
            for a, b in zip(xs, xs[1:]):
                self.assertGreaterEqual(b - a, 59.0)
            self.assertGreaterEqual(len(labels), int(tab.viewport_px() // 400))
            self.assertLessEqual(min(xs), 90)                  # a label near the left edge

    def test_shift_wheel_scrolls_sideways(self):
        self._tracks(3)
        tab = self.tab
        view = tab.view
        view.set_px_per_sec(300)
        tab.scroll_to_px(0, force=True)
        waveform = list(tab.track_strips.values())[0].waveform
        self._wheel(waveform, 100, -120, "<Shift-MouseWheel>")
        self.assertGreater(tab.scroll_px, 0.0)
        right = tab.scroll_px
        self._wheel(waveform, 100, 120, "<Shift-MouseWheel>")
        self.assertLess(tab.scroll_px, right)

    def test_scroll_is_clamped(self):
        self._tracks(1)
        tab = self.tab
        tab.scroll_to_px(-500)
        self.assertEqual(tab.scroll_px, 0.0)
        tab.scroll_to_px(1e9)
        self.assertEqual(tab.scroll_px, tab.max_scroll_px())
        lo, hi = tab.hscroll.get()
        self.assertAlmostEqual(hi, 1.0, places=6)

    def test_ruler_click_sets_playhead(self):
        self._tracks(1)
        tab = self.tab
        tab.view.set_px_per_sec(200)
        tab.scroll_to_px(400, force=True)
        self._settle()
        tab.ruler.event_generate("<Button-1>", x=300, y=10)
        self._settle()
        expected = tab.view.px_to_sec(tab.scroll_px + 300)
        self.assertAlmostEqual(self.app.engine.playhead / self.app.engine.sample_rate, expected, delta=0.01)

    # --------------------------------------------------------- follow playhead
    def test_follow_playhead_scrolls_only_when_it_leaves_the_view(self):
        self._tracks(1)
        tab, view = self.tab, self.tab.view
        view.set_px_per_sec(100)
        tab.scroll_to_px(0, force=True)
        vp = tab.viewport_px()
        inside = (vp * 0.5) / 100.0
        tab.set_playhead(inside)
        self.assertEqual(tab.scroll_px, 0.0)               # inside the window: no scrolling
        outside = (vp + 600) / 100.0
        tab.set_playhead(outside)
        self.assertGreater(tab.scroll_px, 0.0)
        self.assertTrue(tab.scroll_px <= view.sec_to_px(outside) <= tab.scroll_px + vp)
        # playhead keeps moving inside the new window: no more scrolling
        now = tab.scroll_px
        tab.set_playhead(outside + 0.2)
        self.assertEqual(tab.scroll_px, now)
        # rewinding to the start brings the start back into view
        tab.set_playhead(0.0)
        self.assertEqual(tab.scroll_px, 0.0)

    def test_stopped_playhead_does_not_pull_the_view_back(self):
        self._tracks(1)
        tab = self.tab
        tab.view.set_px_per_sec(100)
        tab.set_playhead(1.0)
        away = tab.max_scroll_px()
        self.assertGreater(away, 500.0)
        tab.scroll_to_px(away, force=True)
        for _ in range(5):                                 # the app calls this every 60 ms
            tab.set_playhead(1.0)
        self.assertEqual(tab.scroll_px, away)

    def test_follow_can_be_switched_off(self):
        self._tracks(1)
        tab = self.tab
        tab.view.set_px_per_sec(100)
        tab.follow_var.set(False)
        tab.set_playhead((tab.viewport_px() + 900) / 100.0)
        self.assertEqual(tab.scroll_px, 0.0)

    def test_playhead_line_on_ruler_and_waveforms(self):
        self._tracks(2)
        tab = self.tab
        tab.view.set_px_per_sec(100)
        tab.set_playhead(2.0)
        self._settle()
        x_ruler = tab.ruler.coords(tab.ruler.playhead_line)[0]
        self.assertAlmostEqual(x_ruler, 200.0 - tab.scroll_px, places=3)
        for strip in tab.track_strips.values():
            self.assertAlmostEqual(strip.waveform.coords("playhead")[0], 200.0 - tab.scroll_px, places=3)

    def test_recording_strip_redraw_and_state_refresh(self):
        tracks = self._tracks(2)
        tracks[0].recording = True
        tracks[0].buffer = np.zeros(0, dtype=np.float32)
        self.tab.redraw_recording()
        self._settle()
        texts = [list(self.tab.track_strips.values())[0].waveform.itemcget(i, "text")
                 for i in list(self.tab.track_strips.values())[0].waveform.find_all()
                 if list(self.tab.track_strips.values())[0].waveform.type(i) == "text"]
        self.assertTrue(any("RECORDING" in t for t in texts))
        tracks[0].recording = False
        self.tab.refresh_states()
        self._settle()

    # ---------------------------------------------------- drawing stays bounded
    def test_deep_zoom_on_a_long_clip_draws_only_the_window(self):
        sr = self.app.engine.sample_rate
        self.app.add_empty_track()
        t = self.app.engine.tracks[0]
        t.buffer = np.random.default_rng(3).uniform(-1, 1, sr * 600).astype(np.float32)   # 10 minutes
        self.tab.redraw_all()
        tab = self.tab
        tab.view.set_px_per_sec(2000)                      # clip is 1.2 million px wide
        tab.scroll_to_px(2000 * 300, force=True)           # middle of the clip
        self._settle()
        waveform = list(tab.track_strips.values())[0].waveform
        poly = [i for i in waveform.find_withtag("clip") if waveform.type(i) == "polygon"]
        self.assertEqual(len(poly), 1)
        n_points = len(waveform.coords(poly[0])) // 2
        self.assertLessEqual(n_points, 2 * (waveform.winfo_width() + 3))
        self.assertGreater(n_points, 100)

    def test_clip_scrolled_out_of_view_draws_no_waveform(self):
        self._tracks(1, seconds=(5,), offsets=(0.0,))
        tab = self.tab
        tab.view.set_px_per_sec(100)
        tab.scroll_to_px(2000, force=True)
        self._settle()
        waveform = list(tab.track_strips.values())[0].waveform
        self.assertFalse([i for i in waveform.find_withtag("clip")])

    def test_dragging_a_clip_still_moves_it(self):
        tracks = self._tracks(1, seconds=(5,), offsets=(0.0,))
        tab = self.tab
        tab.view.set_px_per_sec(100)
        self._settle()
        waveform = list(tab.track_strips.values())[0].waveform
        waveform.event_generate("<ButtonPress-1>", x=200, y=40)
        waveform.event_generate("<B1-Motion>", x=300, y=40)
        waveform.event_generate("<ButtonRelease-1>", x=300, y=40)
        self._settle()
        self.assertAlmostEqual(tracks[0].offset / self.app.engine.sample_rate, 1.0, delta=0.05)

    # ------------------------------------------------- old view model still works
    def test_ruler_and_waveform_accept_the_old_view_model(self):
        import waveform_widget as ww
        from track import Track
        root = tk.Toplevel(self.root)
        try:
            old = ww.TimelineView(px_per_sec=80.0)
            ruler = ww.TimelineRuler(root, old, 44100, width_px=1200)
            ruler.pack()
            track = Track("old", 44100)
            track.buffer = np.random.default_rng(0).uniform(-1, 1, 44100 * 3).astype(np.float32)
            canvas = ww.WaveformCanvas(root, track, old, lambda: None, width_px=1200)
            canvas.pack()
            old.zoom(2.0)
            ruler.redraw()
            canvas.redraw()
            self.assertFalse(ruler.virtual)
            self.assertEqual(int(canvas.cget("height")), ww.TRACK_ROW_HEIGHT)
            self.assertGreater(len(canvas.find_withtag("clip")), 0)
        finally:
            root.destroy()

    def test_old_tracks_tab_still_builds(self):
        import tabs
        old = tabs.TracksTab(self.app.notebook, self.app)
        try:
            old.add_track_strip(self.app.engine.tracks[0]) if self.app.engine.tracks else None
            old.rebuild_all()
            old.redraw_all()
        finally:
            old.destroy()


if __name__ == "__main__":
    unittest.main()
