"""Phase 9 / T015: clip editing aids in the Tracks tab: snapping, Shift fine drag, selection,
arrow-key nudge, offset readout, double-click (FX dialog / rename). The snapping maths needs no
Tk; the rest builds LiveLooperApp under Xvfb with the sounddevice stub."""
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

SHIFT, ALT = 0x1, 0x8
B1 = 0x100          # button 1 held, for <B1-Motion>


class ClipMathTests(unittest.TestCase):
    def test_snaps_clip_start_to_a_candidate_within_threshold(self):
        from waveform_widget import snap_offset
        self.assertAlmostEqual(snap_offset(2.03, [2.0, 5.0], 0.05), 2.0)

    def test_does_not_snap_beyond_threshold(self):
        from waveform_widget import snap_offset
        self.assertAlmostEqual(snap_offset(2.2, [2.0], 0.05), 2.2)

    def test_snaps_clip_end_to_a_candidate(self):
        from waveform_widget import snap_offset
        # clip 3 s long starting at 1.98 ends at 4.98: snaps so the end lands on 5.0
        self.assertAlmostEqual(snap_offset(1.98, [5.0], 0.05, duration_sec=3.0), 2.0)

    def test_picks_the_closest_candidate(self):
        from waveform_widget import snap_offset
        self.assertAlmostEqual(snap_offset(2.04, [2.0, 2.06], 0.1), 2.06)

    def test_never_returns_a_negative_offset(self):
        from waveform_widget import snap_offset, snap_offset_info
        self.assertEqual(snap_offset(-0.5, [], 0.05), 0.0)
        self.assertEqual(snap_offset_info(0.02, [-0.01], 0.05)[1], None)

    def test_info_reports_the_target(self):
        from waveform_widget import snap_offset_info
        self.assertEqual(snap_offset_info(1.01, [1.0], 0.05)[1], 1.0)
        self.assertIsNone(snap_offset_info(3.0, [1.0], 0.05)[1])

    def test_fine_drag_is_ten_times_slower(self):
        from waveform_widget import drag_offset
        normal = drag_offset(0, 100, 100.0, 44100)
        fine = drag_offset(0, 100, 100.0, 44100, fine=True)
        self.assertEqual(normal, 44100)
        self.assertEqual(fine, 4410)

    def test_drag_and_nudge_never_go_below_zero(self):
        from waveform_widget import drag_offset, nudge_offset
        self.assertEqual(drag_offset(1000, -500, 100.0, 44100), 0)
        self.assertEqual(nudge_offset(100, -441), 0)
        self.assertEqual(nudge_offset(100, 441), 541)

    def test_readout_text_has_seconds_and_ms(self):
        from waveform_widget import format_offset
        self.assertEqual(format_offset(66150, 44100), "1.500 s  (1500 ms)")


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class ClipEditTabTests(unittest.TestCase):
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
        self.app.cancel_timers()
        self.root.geometry("1366x768+0+0")
        self.tab = self.app.tracks_tab
        self.sr = self.app.engine.sample_rate
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

    def _tracks(self, seconds=(5, 4, 3), offsets=(0.0, 8.0, 14.0), px_per_sec=100):
        for i, sec in enumerate(seconds):
            self.app.add_empty_track()
            t = self.app.engine.tracks[-1]
            t.buffer = np.full(int(self.sr * sec), 0.3, dtype=np.float32)
            t.peaks_cache = None
            t.offset = int(self.sr * offsets[i])
        self.tab.view.set_px_per_sec(px_per_sec)
        self.tab.redraw_all()
        self._settle()
        return self.app.engine.tracks

    def _wf(self, i):
        return self.tab.track_strips[self.app.engine.tracks[i].id].waveform

    def _press(self, wf, x, state=0, y=40):
        wf.event_generate("<ButtonPress-1>", x=x, y=y, state=state)

    def _move(self, wf, x, state=0, y=40):
        wf.event_generate("<B1-Motion>", x=x, y=y, state=state | B1)
        self._settle(2)

    def _release(self, wf, x, state=0, y=40):
        wf.event_generate("<ButtonRelease-1>", x=x, y=y, state=state)
        self._settle(2)

    # ------------------------------------------------------------ drag + snap
    def test_drag_snaps_to_another_clips_edge(self):
        tracks = self._tracks()
        wf = self._wf(0)                    # clip 0: 0..5 s; clip 1 starts at 8 s
        # grab at x=100 (1 s), drag so the clip end would be at 7.97 s (3 px from clip 1 start)
        self._press(wf, 100)
        self._move(wf, 100 + 297)
        self.assertAlmostEqual(tracks[0].offset / self.sr + 5.0, 8.0, places=2)   # end snapped to 8.0
        self._release(wf, 397)

    def test_drag_snaps_to_the_playhead(self):
        tracks = self._tracks()
        self.tab.set_playhead(3.0)
        self._settle()
        wf = self._wf(0)
        self._press(wf, 100)
        self._move(wf, 100 + 303)           # start would be 3.03 s, playhead at 3.0 s
        self.assertAlmostEqual(tracks[0].offset / self.sr, 3.0, places=3)
        self._release(wf, 403)

    def test_drag_does_not_snap_when_far_and_shift_or_alt_bypass(self):
        tracks = self._tracks()
        self.tab.set_playhead(3.0)
        wf = self._wf(0)
        self._press(wf, 100)
        self._move(wf, 100 + 340)           # 3.40 s: more than 8 px from 3.0
        self.assertAlmostEqual(tracks[0].offset / self.sr, 3.4, places=2)
        self._move(wf, 100 + 303, state=ALT)   # Alt: no snap, normal speed
        self.assertAlmostEqual(tracks[0].offset / self.sr, 3.03, places=2)
        self._release(wf, 403)

    def test_shift_drag_moves_ten_times_slower(self):
        tracks = self._tracks(offsets=(1.0, 20.0, 30.0))
        wf = self._wf(0)
        self._press(wf, 150, state=SHIFT)
        self._move(wf, 150 + 100, state=SHIFT)     # pointer moved 1.00 s
        self.assertAlmostEqual(tracks[0].offset / self.sr, 1.1, places=3)   # clip moved 0.10 s
        self._release(wf, 250, state=SHIFT)

    def test_drag_calls_on_change_so_loop_end_is_recomputed(self):
        self._tracks()
        calls = []
        self.app.engine._recompute_loop_end = lambda: calls.append(1)
        wf = self._wf(0)
        self._press(wf, 100)
        self._move(wf, 160)
        self._release(wf, 160)
        self.assertTrue(calls)

    def test_press_outside_the_clip_does_not_drag(self):
        tracks = self._tracks()
        wf = self._wf(0)                    # clip is 0..500 px
        before = tracks[0].offset
        self._press(wf, 900)
        self._move(wf, 950)
        self._release(wf, 950)
        self.assertEqual(tracks[0].offset, before)

    def test_recording_track_cannot_be_dragged(self):
        tracks = self._tracks()
        tracks[0].recording = True
        wf = self._wf(0)
        before = tracks[0].offset
        self._press(wf, 100)
        self._move(wf, 200)
        self._release(wf, 200)
        tracks[0].recording = False
        self.assertEqual(tracks[0].offset, before)

    # ------------------------------------------------------------ readout
    def test_readout_shows_during_drag_and_is_gone_after_release(self):
        self._tracks()
        wf = self._wf(0)
        self._press(wf, 100)
        self._move(wf, 160)
        items = wf.find_withtag("readout")
        self.assertTrue(items)
        texts = [wf.itemcget(i, "text") for i in items if wf.type(i) == "text"]
        self.assertTrue(texts and " s  (" in texts[0] and texts[0].endswith(" ms)"))
        self._release(wf, 160)
        self.assertFalse(wf.find_withtag("readout"))

    # ------------------------------------------------------------ selection
    def test_click_selects_one_clip_and_empty_space_clears(self):
        tracks = self._tracks()
        wf0, wf1 = self._wf(0), self._wf(1)
        self._press(wf0, 100)
        self._release(wf0, 100)
        self.assertEqual(self.tab.selected_track_id, tracks[0].id)
        self.assertTrue(wf0.find_withtag("selection"))
        self.assertFalse(wf1.find_withtag("selection"))
        x1 = int(8.0 * 100 + 50)            # inside clip 1 (offset 8 s)
        self._press(wf1, x1)
        self._release(wf1, x1)
        self.assertEqual(self.tab.selected_track_id, tracks[1].id)
        self.assertFalse(wf0.find_withtag("selection"))
        self.assertTrue(wf1.find_withtag("selection"))
        self._press(wf1, 100)               # empty space on track 1 (its clip starts at 8 s)
        self._release(wf1, 100)
        self.assertIsNone(self.tab.selected_track_id)
        self.assertFalse(wf1.find_withtag("selection"))

    def test_selection_is_not_saved_in_the_track_data(self):
        tracks = self._tracks()
        wf = self._wf(0)
        self._press(wf, 100)
        self._release(wf, 100)
        self.assertNotIn("selected", tracks[0].to_meta_dict())

    # ------------------------------------------------------------ arrow keys
    def _key(self, keysym, state=0, widget=None):
        self.root.focus_force()
        self._settle(2)
        (widget or self.root).event_generate(f"<{keysym}>", state=state)
        self._settle(2)

    def _select(self, i):
        wf = self._wf(i)
        t = self.app.engine.tracks[i]
        x = int(t.offset / self.sr * 100 + 20)
        self._press(wf, x)
        self._release(wf, x)

    def test_arrows_nudge_selected_clip_by_10ms_and_100ms(self):
        tracks = self._tracks(offsets=(1.0, 20.0, 30.0))
        self._select(0)
        base = tracks[0].offset
        self._key("Right")
        self.assertEqual(tracks[0].offset - base, int(round(0.010 * self.sr)))
        self._key("Right", state=SHIFT)
        self.assertEqual(tracks[0].offset - base, int(round(0.010 * self.sr)) + int(round(0.100 * self.sr)))
        self._key("Left", state=SHIFT)
        self._key("Left")
        self.assertEqual(tracks[0].offset, base)

    def test_arrow_never_goes_below_zero(self):
        tracks = self._tracks(offsets=(0.005, 20.0, 30.0))
        self._select(0)
        self._key("Left")
        self.assertEqual(tracks[0].offset, 0)
        self._key("Left", state=SHIFT)
        self.assertEqual(tracks[0].offset, 0)

    def test_arrow_with_no_selection_does_nothing(self):
        tracks = self._tracks()
        before = [t.offset for t in tracks]
        self._key("Right")
        self.assertEqual([t.offset for t in tracks], before)

    def test_arrow_does_not_fire_while_a_text_entry_has_focus(self):
        tracks = self._tracks(offsets=(1.0, 20.0, 30.0))
        self._select(0)
        base = tracks[0].offset
        entry = self.tab.track_strips[tracks[0].id].header.name_entry
        entry.focus_force()
        self._settle(2)
        entry.event_generate("<Right>")
        self._settle(2)
        self.assertEqual(tracks[0].offset, base)

    def test_arrow_nudge_recomputes_loop_end_and_shows_a_readout(self):
        self._tracks(offsets=(1.0, 20.0, 30.0))
        calls = []
        self.app.engine._recompute_loop_end = lambda: calls.append(1)
        self._select(0)
        self._key("Right")
        self.assertTrue(calls)
        self.assertTrue(self._wf(0).find_withtag("readout"))
        self.tab._clear_readouts()
        self.assertFalse(self._wf(0).find_withtag("readout"))

    def test_space_r_home_shortcuts_still_bound(self):
        for seq in ("<space>", "r", "R", "<Home>"):
            self.assertTrue(self.root.bind_all(seq), seq)

    # ------------------------------------------------------------ double click
    def _double_click(self, wf, x, y):
        for _ in range(2):
            wf.event_generate("<ButtonPress-1>", x=x, y=y)
            wf.event_generate("<ButtonRelease-1>", x=x, y=y)
        self._settle(3)

    def test_double_click_on_clip_opens_fx_dialog(self):
        tracks = self._tracks()
        opened = []
        self.app.open_fx = lambda track: opened.append(track)
        wf = self._wf(0)
        self._double_click(wf, 300, 60)               # clip body, below the name label
        self.assertEqual(opened, [tracks[0]])

    def test_double_click_on_empty_space_does_not_open_fx(self):
        self._tracks()
        opened = []
        self.app.open_fx = lambda track: opened.append(track)
        self._double_click(self._wf(0), 1200, 60)
        self.assertEqual(opened, [])

    def test_double_click_on_name_focuses_the_name_entry(self):
        tracks = self._tracks()
        opened = []
        self.app.open_fx = lambda track: opened.append(track)
        wf = self._wf(0)
        lx0, ly0, lx1, ly1 = wf.bbox("label")
        self.root.focus_force()
        self._double_click(wf, int((lx0 + lx1) / 2), int((ly0 + ly1) / 2))
        entry = self.tab.track_strips[tracks[0].id].header.name_entry
        self.assertIs(self.root.focus_lastfor(), entry)
        self.assertEqual(opened, [])

    # ------------------------------------------------------------ misc
    def test_removing_the_selected_track_clears_the_selection(self):
        tracks = self._tracks()
        self._select(0)
        self.assertEqual(self.tab.selected_track_id, tracks[0].id)
        self.app.remove_track(tracks[0])
        self._settle()
        self.assertIsNone(self.tab.selected_track_id)


if __name__ == "__main__":
    unittest.main()
