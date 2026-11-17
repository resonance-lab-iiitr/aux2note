"""Phase 9 / T009: timeline view model (pure Python, no Tk)."""
import unittest

from tests import _stubs  # noqa: F401
from timeline_view import (TimelineView, ruler_ticks, ruler_step, format_time,
                           MIN_PX_PER_SEC, MAX_PX_PER_SEC, HEIGHT_LEVELS)


class ZoomTests(unittest.TestCase):
    def test_old_interface_still_there(self):
        v = TimelineView(px_per_sec=80.0)
        self.assertEqual(v.sec_to_px(2), 160.0)
        self.assertEqual(v.px_to_sec(160), 2.0)
        hits = []
        v.add_listener(lambda: hits.append(1))
        v.zoom(1.25)
        self.assertEqual(v.px_per_sec, 100.0)
        self.assertEqual(hits, [1])

    def test_limits_hold_after_any_zoom(self):
        v = TimelineView()
        for f in (100, 100, 100, 100):
            v.zoom(f)
        self.assertEqual(v.px_per_sec, MAX_PX_PER_SEC)
        for f in (0.01, 0.01, 0.01, 0.01):
            v.zoom(f)
        self.assertEqual(v.px_per_sec, MIN_PX_PER_SEC)
        self.assertEqual(TimelineView(px_per_sec=1e9).px_per_sec, MAX_PX_PER_SEC)
        self.assertEqual(TimelineView(px_per_sec=-5).px_per_sec, MIN_PX_PER_SEC)
        v.set_px_per_sec(0)
        self.assertEqual(v.px_per_sec, MIN_PX_PER_SEC)

    def test_zoom_at_keeps_time_under_mouse(self):
        for pps in (10, 80, 500):
            for factor in (1.25, 0.8, 2.0, 0.5):
                for scroll, mouse in ((0.0, 0), (0.0, 300), (1234.0, 417), (5000.0, 999)):
                    v = TimelineView(px_per_sec=pps)
                    t_before = (scroll + mouse) / v.px_per_sec
                    new_scroll = v.zoom_at(factor, mouse, scroll)
                    self.assertGreaterEqual(new_scroll, 0.0)
                    if new_scroll > 0.0:   # not pinned at the left edge
                        screen_x = v.sec_to_px(t_before) - new_scroll
                        self.assertLess(abs(screen_x - mouse), 1.0, (pps, factor, scroll, mouse))

    def test_zoom_at_clamped_at_limit_does_not_drift(self):
        v = TimelineView(px_per_sec=MAX_PX_PER_SEC)
        self.assertEqual(v.zoom_at(2.0, 200, 700.0), 700.0)   # already at max: same scroll

    def test_zoom_at_never_negative_scroll(self):
        v = TimelineView(px_per_sec=100)
        self.assertEqual(v.zoom_at(0.5, 400, 0.0), 0.0)

    def test_listener_called_only_on_change_and_isolated(self):
        v = TimelineView(px_per_sec=MAX_PX_PER_SEC)
        hits = []
        v.add_listener(lambda: 1 / 0)
        v.add_listener(lambda: hits.append(1))
        v.zoom(2.0)                      # clamped, no change
        self.assertEqual(hits, [])
        v.zoom(0.5)
        self.assertEqual(hits, [1])


class FitTests(unittest.TestCase):
    def test_fit_shows_whole_length_with_margin(self):
        v = TimelineView()
        scroll = v.fit(30.0, 1000)
        self.assertEqual(scroll, 0.0)
        width = v.sec_to_px(30.0)
        self.assertLess(width, 1000)            # margin left
        self.assertGreater(width, 900)          # but nearly fills the window

    def test_fit_clamps_and_ignores_empty(self):
        v = TimelineView(px_per_sec=123.0)
        v.fit(0, 1000)
        self.assertEqual(v.px_per_sec, 123.0)
        v.fit(5, 0)
        self.assertEqual(v.px_per_sec, 123.0)
        v.fit(100000, 1000)
        self.assertEqual(v.px_per_sec, MIN_PX_PER_SEC)
        v.fit(0.01, 1000)
        self.assertEqual(v.px_per_sec, MAX_PX_PER_SEC)

    def test_visible_range(self):
        v = TimelineView(px_per_sec=100)
        self.assertEqual(v.visible_range(0, 1000), (0.0, 10.0))
        self.assertEqual(v.visible_range(250, 500), (2.5, 7.5))
        self.assertEqual(v.visible_range(-10, 100)[0], 0.0)


class HeightTests(unittest.TestCase):
    def test_default_is_old_row_height(self):
        self.assertEqual(TimelineView().track_height, 96)

    def test_step_up_down_and_clamp(self):
        v = TimelineView()
        seen = [v.track_height]
        for _ in range(10):
            seen.append(v.height_up())
        self.assertEqual(seen[-1], HEIGHT_LEVELS[-1])
        self.assertEqual(seen[:3], [96, 140, 200])
        for _ in range(10):
            v.height_down()
        self.assertEqual(v.track_height, HEIGHT_LEVELS[0])
        self.assertEqual(list(HEIGHT_LEVELS), sorted(HEIGHT_LEVELS))

    def test_height_change_notifies_once(self):
        v = TimelineView()
        hits = []
        v.add_listener(lambda: hits.append(1))
        v.height_up()
        v.set_height_level(99)           # clamps to max, a change from level 3
        v.set_height_level(99)           # no change
        self.assertEqual(len(hits), 2)


class RulerTests(unittest.TestCase):
    def test_ticks_are_readable_at_every_zoom(self):
        zooms = [4, 5, 7.5, 10, 15, 20, 33, 50, 80, 120, 250, 500, 999, 1500, 2000]
        for pps in zooms:
            for scroll in (0.0, 777.0, 123456.0):
                ticks = ruler_ticks(pps, 1200, scroll)
                self.assertGreater(len(ticks), 2, pps)
                gaps = [b.x - a.x for a, b in zip(ticks, ticks[1:])]
                self.assertGreaterEqual(min(gaps), 60.0 - 1e-6, (pps, scroll))
                labels = [t.label for t in ticks]
                self.assertEqual(len(labels), len(set(labels)), (pps, scroll, labels[:5]))
                # Visible range is fully covered.
                self.assertLessEqual(ticks[0].x, scroll + 1e-6 if scroll > 0 else 1e-6)
                self.assertGreaterEqual(ticks[-1].x, scroll + 1200 - 1e-6)

    def test_steps_are_nice(self):
        self.assertEqual(ruler_step(80), 1)       # 80 px per 1 s
        self.assertEqual(ruler_step(40), 2)
        self.assertEqual(ruler_step(10), 10)
        self.assertEqual(ruler_step(4), 15)
        self.assertEqual(ruler_step(2000), 0.05)
        for pps in range(4, 2001, 7):
            step = ruler_step(pps)
            self.assertIn(step, (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300))

    def test_labels(self):
        self.assertEqual(format_time(0, 1), "0:00")
        self.assertEqual(format_time(75, 15), "1:15")
        self.assertEqual(format_time(3725, 60), "1:02:05")
        self.assertEqual(format_time(0.3, 0.1), "0:00.3")
        self.assertEqual(format_time(1.25, 0.05), "0:01.25")
        self.assertEqual(format_time(59.96, 1), "1:00")           # rounds, never "0:60"
        ticks = TimelineView(px_per_sec=2000).ticks(300, 0)
        self.assertEqual([t.label for t in ticks[:3]], ["0:00.00", "0:00.05", "0:00.10"])

    def test_first_tick_is_zero_and_majors(self):
        ticks = ruler_ticks(80, 800, 0)
        self.assertEqual(ticks[0].sec, 0)
        self.assertTrue(ticks[0].major)
        self.assertEqual([t.major for t in ticks[:6]], [True, False, False, False, False, True])


class PersistenceTests(unittest.TestCase):
    def test_round_trip(self):
        v = TimelineView(px_per_sec=333.0, height_level=3)
        w = TimelineView.from_dict(v.to_dict())
        self.assertEqual(w.to_dict(), v.to_dict())
        self.assertEqual(w.track_height, 140)

    def test_bad_data_falls_back(self):
        for bad in (None, "x", {}, {"px_per_sec": "abc"}, {"px_per_sec": float("nan")},
                    {"height_level": None}, {"height_level": 99, "px_per_sec": 1e12}):
            w = TimelineView.from_dict(bad)
            self.assertTrue(MIN_PX_PER_SEC <= w.px_per_sec <= MAX_PX_PER_SEC)
            self.assertTrue(0 <= w.height_level < len(HEIGHT_LEVELS))


if __name__ == "__main__":
    unittest.main()
