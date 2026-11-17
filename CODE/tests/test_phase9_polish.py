"""Phase 9 / T028: GUI polish from the Phase 9 audit.
(1) MASTER FX fully visible at 1366x768, scale 1.0. (2) VOL and PAN sliders do not overlap at
row height 96 (scale 1.0 and 1.5). (3) Track.peak exists right after creation."""
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


class TrackPeakTests(unittest.TestCase):
    def test_peak_is_zero_right_after_creation(self):
        from track import Track
        t = Track("X", 44100)
        self.assertEqual(t.peak, 0.0)
        self.assertIsInstance(t.peak, float)

    def test_engine_still_writes_peak(self):
        import audio_engine
        src = open(audio_engine.__file__, encoding="utf-8").read()
        self.assertIn("t.peak = _abs_peak(samples) * t.gain", src)


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class PolishAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import settings_store
        cls._orig_save = settings_store.save_settings
        settings_store.save_settings = lambda data, *a, **k: True

    @classmethod
    def tearDownClass(cls):
        import settings_store
        settings_store.save_settings = cls._orig_save

    def setUp(self):
        import ui_theme
        from app import LiveLooperApp
        self.theme = ui_theme
        ui_theme.set_scale(1.0)
        self.root = tk.Tk()
        self.app = LiveLooperApp(self.root)
        self.app.cancel_timers()
        self.root.geometry("1366x768+0+0")
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

    def _find_button(self, text):
        def walk(w):
            for c in w.winfo_children():
                try:
                    if c.cget("text") == text:
                        return c
                except tk.TclError:
                    pass
                r = walk(c)
                if r is not None:
                    return r
            return None
        return walk(self.app.top_bar)

    def _header(self, n=1):
        for i in range(n):
            self.app.add_empty_track()
        self.app.select_tab("tracks")
        self._settle()
        return next(iter(self.app.tracks_tab.track_strips.values())).header

    # ------------------------------------------------------------------ (1) top bar
    def test_master_fx_text_is_fully_visible_at_1366(self):
        btn = self._find_button("MASTER FX")
        self.assertIsNotNone(btn)
        self.assertGreaterEqual(btn.winfo_width(), btn.winfo_reqwidth())
        self.assertGreaterEqual(btn.winfo_rootx(), 0)
        self.assertLessEqual(btn.winfo_rootx() + btn.winfo_width(),
                             self.root.winfo_rootx() + self.root.winfo_width())

    def test_every_top_bar_button_fits_inside_the_window(self):
        right = self.root.winfo_rootx() + self.root.winfo_width()
        for text in ("MASTER FX", "+ TRACK", "IMPORT", "EXPORT MIX \u2193"):
            b = self._find_button(text)
            self.assertIsNotNone(b, text)
            self.assertGreaterEqual(b.winfo_width(), b.winfo_reqwidth(), text)
            self.assertLessEqual(b.winfo_rootx() + b.winfo_width(), right, text)

    def test_narrow_window_wraps_the_button_group(self):
        self.root.geometry("1000x768+0+0")
        self._settle(10)
        self.assertTrue(self.app._top_bar_needs_wrap() or
                        self.app.top_right.winfo_manager() == "pack")
        b = self._find_button("MASTER FX")
        self.assertGreaterEqual(b.winfo_width(), b.winfo_reqwidth())

    # ------------------------------------------------------------------ (2) sliders
    def _boxes_overlap(self, a, b):
        ax0, ay0 = a.winfo_x(), a.winfo_y()
        ax1, ay1 = ax0 + a.winfo_height() * 0 + a.winfo_width(), ay0 + a.winfo_height()
        bx0, by0 = b.winfo_x(), b.winfo_y()
        bx1, by1 = bx0 + b.winfo_width(), by0 + b.winfo_height()
        return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1

    def _check_sliders(self, scale):
        self.theme.set_scale(scale)
        self._settle()
        h = self._header()
        self._settle()
        self.assertTrue(h.vol_scale.winfo_ismapped())
        self.assertTrue(h.pan_scale.winfo_ismapped())
        self.assertFalse(self._boxes_overlap(h.vol_scale, h.pan_scale),
                         (scale, h.vol_scale.winfo_geometry(), h.pan_scale.winfo_geometry()))
        # both stay inside the control column
        col_h = h._col.winfo_height()
        self.assertLessEqual(h.pan_scale.winfo_y() + h.pan_scale.winfo_height(), col_h)

    def test_vol_and_pan_do_not_overlap_at_scale_1(self):
        self._check_sliders(1.0)

    def test_vol_and_pan_do_not_overlap_at_scale_1_5(self):
        self._check_sliders(1.5)

    def test_readouts_have_room_for_five_characters(self):
        h = self._header()
        self.assertGreaterEqual(int(h.vol_readout.cget("width")), 5)
        self.assertGreaterEqual(int(h.pan_readout.cget("width")), 5)
        self.assertEqual(h._fmt_vol(1.0), "1.00x")


if __name__ == "__main__":
    unittest.main()
