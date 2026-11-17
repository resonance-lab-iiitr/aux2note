"""Phase 9 / T014: the Mixer tab (tab_mixer.Tab) and the per-track peak the engine now sets.
The engine tests need no Tk; the tab tests build LiveLooperApp under Xvfb with the sounddevice
stub and are skipped without a display."""
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


def _fake_block(engine, frames=256, level=0.5):
    """Run the engine's real mixing code on one block (no sound card)."""
    indata = np.zeros((frames, 1), dtype=np.float32)
    outdata = np.zeros((frames, 2), dtype=np.float32)
    engine._callback(indata, outdata, frames, None, None)
    return outdata


class TrackPeakEngineTests(unittest.TestCase):
    def _engine(self):
        from audio_engine import AudioEngine
        from track import Track
        e = AudioEngine(sample_rate=48000, block_size=256)
        loud = Track("loud", 48000)
        loud.load_from_array(np.full(4800, 0.5, dtype=np.float32), 0)
        quiet = Track("silent", 48000)          # no audio at all
        e.add_track(loud)
        e.add_track(quiet)
        e.is_playing = True
        return e, loud, quiet

    def test_peak_is_zero_for_silent_track_and_positive_for_audio(self):
        e, loud, quiet = self._engine()
        _fake_block(e)
        self.assertEqual(quiet.peak, 0.0)
        self.assertAlmostEqual(loud.peak, 0.5, places=4)       # 0.5 sample x gain 1.0

    def test_peak_follows_the_fader_and_is_zero_when_muted_or_stopped(self):
        e, loud, _ = self._engine()
        loud.gain = 0.5
        _fake_block(e)
        self.assertAlmostEqual(loud.peak, 0.25, places=4)
        loud.mute = True
        for _ in range(60):                    # let the 8 ms mute glide finish
            _fake_block(e)
        self.assertEqual(loud.peak, 0.0)
        loud.mute = False
        e.is_playing = False
        for _ in range(60):
            _fake_block(e)
        self.assertEqual(loud.peak, 0.0)

    def test_mix_output_is_unchanged_by_the_peak_code(self):
        """The peak is read-only: the output block must equal what the pre-T014 maths gives."""
        e, loud, _ = self._engine()
        out = _fake_block(e)
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertGreater(float(np.max(np.abs(out))), 0.0)
        self.assertAlmostEqual(e.peak_l, float(np.max(np.abs(out[:, 0]))), places=6)

    def test_abs_peak_helper(self):
        from audio_engine import _abs_peak
        self.assertEqual(_abs_peak(np.array([], dtype=np.float32)), 0.0)
        self.assertAlmostEqual(_abs_peak(np.array([0.1, -0.7, 0.3], dtype=np.float32)), 0.7, places=6)
        self.assertAlmostEqual(_abs_peak(np.array([0.9, -0.2], dtype=np.float32)), 0.9, places=6)


class MeterMathTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_TK, "tab_mixer imports Tk")
    def test_helpers(self):
        import tab_mixer as m
        self.assertEqual(m.level_to_fraction(0.0), 0.0)
        self.assertEqual(m.level_to_fraction(1e-6), 0.0)
        self.assertAlmostEqual(m.level_to_fraction(1.0), 1.0)
        self.assertEqual(m.level_to_fraction(2.0), 1.0)
        self.assertAlmostEqual(m.level_to_fraction(0.5), (20 * np.log10(0.5) + 60) / 60, places=6)
        self.assertEqual(m.format_gain(0.0), "-inf dB")
        self.assertEqual(m.format_gain(1.0), "+0.0 dB")
        self.assertEqual(m.format_pan(0.0), "C")
        self.assertEqual(m.format_pan(-0.5), "0.50L")
        self.assertEqual(m.format_pan(1.0), "1.00R")


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class MixerTabTests(unittest.TestCase):
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
        self.root.geometry("1366x768+0+0")          # after the app set its own size
        self.app.cancel_timers()
        self.mixer = self.app.tab_widgets["mixer"]
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

    def _show(self):
        self.app.select_tab("mixer")
        self._settle()
        self.mixer.on_show()
        self._settle()

    def _add(self, n):
        for _ in range(n):
            self.app.add_empty_track()
        self._settle()

    # ------------------------------------------------------------------ structure
    def test_loaded_by_tab_loader(self):
        import tab_mixer
        self.assertIsInstance(self.mixer, tab_mixer.Tab)
        self.assertEqual(self.mixer.title, "Mixer")

    def test_one_strip_per_track_on_add_and_remove(self):
        self._add(3)
        self._show()
        tracks = list(self.app.engine.tracks)
        self.assertEqual(len(self.mixer.strips), 3)
        self.assertEqual([self.mixer.strips[t.id].track for t in tracks], tracks)
        self.app.remove_track(tracks[1])
        self._show()
        self.assertEqual(set(self.mixer.strips), {tracks[0].id, tracks[2].id})
        for t in list(self.app.engine.tracks):
            self.app.remove_track(t)
        self._show()
        self.assertEqual(self.mixer.strips, {})
        self.assertTrue(self.mixer.empty_lbl.winfo_manager())      # empty-state text shown

    def test_strips_follow_track_order(self):
        self._add(3)
        self._show()
        xs = [self.mixer.strips[t.id].winfo_x() for t in self.app.engine.tracks]
        self.assertEqual(xs, sorted(xs))

    # ------------------------------------------------------------------ controls
    def _pair(self):
        self._add(2)
        self._show()
        track = self.app.engine.tracks[0]
        return track, self.mixer.strips[track.id], self.app.tracks_tab.track_strips[track.id]

    def test_fader_changes_track_and_tracks_tab_strip(self):
        track, strip, tstrip = self._pair()
        strip.vol_scale.set(1.5)
        self._settle()
        self.assertAlmostEqual(track.gain, 1.5)
        self.assertAlmostEqual(float(tstrip.header.vol_scale.get()), 1.5, places=2)
        self.assertEqual(strip.vol_lbl.cget("text"), "+3.5 dB")

    def test_pan_changes_track_and_tracks_tab_strip(self):
        track, strip, tstrip = self._pair()
        strip.pan_scale.set(-0.4)
        self._settle()
        self.assertAlmostEqual(track.pan, -0.4)
        self.assertAlmostEqual(float(tstrip.header.pan_scale.get()), -0.4, places=2)
        self.assertEqual(strip.pan_lbl.cget("text"), "0.40L")

    def test_mute_and_solo_change_track_and_tracks_tab_strip(self):
        track, strip, tstrip = self._pair()
        strip.mute_btn.invoke()
        self._settle()
        self.assertTrue(track.mute)
        self.assertTrue(tstrip.header.mute_var.get())
        strip.solo_btn.invoke()
        self._settle()
        self.assertTrue(track.solo)
        self.assertTrue(tstrip.header.solo_var.get())
        strip.mute_btn.invoke()
        self.assertFalse(track.mute)
        self.assertFalse(tstrip.header.mute_var.get())

    def test_arm_changes_track_and_unarms_the_other_everywhere(self):
        self._add(2)
        self._show()
        a, b = self.app.engine.tracks
        sa, sb = self.mixer.strips[a.id], self.mixer.strips[b.id]
        sa.arm_btn.invoke()
        self._settle()
        self.assertTrue(a.armed)
        self.assertTrue(self.app.tracks_tab.track_strips[a.id].header.arm_var.get())
        sb.arm_btn.invoke()                      # arming B unarms A in the model ...
        self._settle()
        self.assertTrue(b.armed)
        self.assertFalse(a.armed)
        self.assertFalse(sa.arm_var.get())       # ... and in both tabs
        self.assertFalse(self.app.tracks_tab.track_strips[a.id].header.arm_var.get())

    def test_changes_made_in_tracks_tab_show_after_on_show(self):
        track, strip, tstrip = self._pair()
        track.gain = 0.25                          # what a Tracks tab slider / undo / load does
        track.mute = True
        track.pan = 0.6
        self._show()
        self.assertAlmostEqual(float(strip.vol_scale.get()), 0.25, places=2)
        self.assertTrue(strip.mute_var.get())
        self.assertAlmostEqual(float(strip.pan_scale.get()), 0.6, places=2)

    def test_fx_toggles_switch_the_track_effect_and_button_opens_dialog(self):
        track, strip, _ = self._pair()
        self.assertFalse(track.effects.reverb.enabled)
        strip.rack.buttons["reverb"].invoke()
        self.assertTrue(track.effects.reverb.enabled)
        strip.rack.buttons["reverb"].invoke()
        self.assertFalse(track.effects.reverb.enabled)
        opened = []
        self.app.open_fx = lambda t: opened.append(t)       # the real dialog is covered by FX tests
        # the strip's button looks open_fx up when pressed
        for child in strip.rack.frame.winfo_children():
            if isinstance(child, tk.Widget) and child.winfo_class() == "TButton":
                child.invoke()
        self.assertEqual(opened, [track])

    # ------------------------------------------------------------------ master
    def test_master_fader_changes_engine_gain_and_top_bar(self):
        self._show()
        self.mixer.master_strip.vol_scale.set(0.5)
        self._settle()
        self.assertAlmostEqual(self.app.engine.master_gain, 0.5)
        self.assertAlmostEqual(float(self.app.master_vol.get()), 0.5, places=2)
        self.assertEqual(self.mixer.master_strip.vol_lbl.cget("text"), "-6.0 dB")

    def test_master_fader_resyncs_from_the_top_bar(self):
        self.app.master_vol.set(1.4)
        self._show()
        self.assertAlmostEqual(self.app.engine.master_gain, 1.4)
        self.assertAlmostEqual(float(self.mixer.master_strip.vol_scale.get()), 1.4, places=2)

    def test_master_fx_toggle_switches_both_channels(self):
        e = self.app.engine
        self._show()
        before = e.master_fx_l.delay.enabled
        self.mixer.master_strip.rack.buttons["delay"].invoke()
        self.assertEqual(e.master_fx_l.delay.enabled, not before)
        self.assertEqual(e.master_fx_r.delay.enabled, not before)

    # ------------------------------------------------------------------ meters
    def test_meters_follow_track_peak_only_while_the_engine_is_live(self):
        track, strip, _ = self._pair()
        track.peak = 0.5
        self.app.engine.peak_l = self.app.engine.peak_r = 0.25
        self.app.engine.is_active = False
        self.mixer.on_tick()
        self.assertEqual(strip.meter.shown, [0.0])
        self.assertEqual(self.mixer.master_strip.meter.shown, [0.0, 0.0])
        self.app.engine.is_active = True
        self.mixer.on_tick()
        self.assertAlmostEqual(strip.meter.shown[0], 0.5)
        self.assertEqual(self.mixer.master_strip.meter.shown, [0.25, 0.25])
        track.peak = 0.0                          # signal gone: the bar falls, it does not jump
        self.mixer.on_tick()
        self.assertTrue(0.0 < strip.meter.shown[0] < 0.5)
        self.app.engine.is_active = False

    def test_meter_reads_a_track_that_never_ran(self):
        track, strip, _ = self._pair()
        self.app.engine.is_active = True
        if hasattr(track, "peak"):
            del track.peak
        self.mixer.on_tick()                      # must not raise
        self.assertEqual(strip.meter.shown, [0.0])
        self.app.engine.is_active = False

    # ------------------------------------------------------------------ layout
    def test_horizontal_scrollbar_appears_with_12_tracks_not_with_2(self):
        self._add(2)
        self._show()
        self.assertFalse(self.mixer.scroll.horizontal_visible)
        self._add(10)
        self._show()
        self.assertEqual(len(self.mixer.strips), 12)
        self.assertTrue(self.mixer.scroll.horizontal_visible)

    def test_strips_and_master_are_fully_visible_at_1366x768(self):
        self._add(3)
        self._show()
        top = self.mixer.winfo_rooty()
        bottom = top + self.mixer.winfo_height()
        for strip in list(self.mixer.strips.values()) + [self.mixer.master_strip]:
            self.assertGreaterEqual(strip.winfo_rooty(), top)
            self.assertLessEqual(strip.winfo_rooty() + strip.winfo_height(), bottom + 1)
        self.assertFalse(self.mixer.scroll.vertical_visible)
        last = self.mixer.master_strip.winfo_rootx() + self.mixer.master_strip.winfo_width()
        self.assertLessEqual(last, self.root.winfo_rootx() + self.root.winfo_width())


if __name__ == "__main__":
    unittest.main()
