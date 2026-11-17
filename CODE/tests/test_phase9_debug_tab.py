"""Phase 9 / T013: the Debug tab (tab_debug.Tab) and the reworked DebugCenter.
Builds LiveLooperApp under Xvfb with the sounddevice stub; skipped without Tk or a display."""
import re
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
class DebugTabTests(unittest.TestCase):
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
        self.app.select_tab("debug")
        self.tab = self.app.tab_widgets["debug"]
        self.dc = self.app.debug_center
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

    def _text(self):
        return self.dc.console.get("1.0", "end")

    def _select(self, idx):
        self.dc.nb.select(idx)
        self._settle()

    def test_debug_tab_is_the_new_class(self):
        import tab_debug
        self.assertIsInstance(self.tab, tab_debug.Tab)
        self.assertTrue(str(self.dc).startswith(str(self.tab)))
        titles = [self.dc.nb.tab(t, "text").strip() for t in self.dc.nb.tabs()]
        self.assertEqual(titles, ["Log", "Engine", "Devices", "Tracks", "Load", "Report"])
        self.assertGreater(self.dc.console.winfo_height(), 200)      # fills the tab, not 4 lines

    def test_search_shows_match_count(self):
        d = self.app.dlog
        for i in range(3):
            d.add(f"needle {i}", "SYS")
        d.add("haystack", "SYS")
        self.dc.pump()
        self.dc.search_var.set("needle")
        self._settle()
        self.assertEqual(self.dc.match_lbl["text"], "3 matches")
        self.assertNotIn("haystack", self._text())
        self.dc.search_var.set("")
        self._settle()
        self.assertIn("lines", self.dc.match_lbl["text"])
        self.assertIn("haystack", self._text())

    def test_level_chips_filter(self):
        d = self.app.dlog
        d.add("just info", "SYS")
        d.add("real problem", "ERROR")
        self.dc.pump()
        self.assertIn("just info", self._text())
        self.dc.level_chips["ERROR"].invoke()
        self._settle()
        self.assertEqual(self.dc.level_var.get(), "ERROR")
        self.assertNotIn("just info", self._text())
        self.assertIn("real problem", self._text())
        self.dc.level_chips["DEBUG"].invoke()
        self.assertIn("just info", self._text())

    def test_autoscroll_pause_and_clear(self):
        d = self.app.dlog
        for i in range(200):
            d.add(f"row {i}", "SYS")
        self.dc.pump()
        self._settle()
        self.assertGreater(self.dc.console.yview()[0], 0.2)           # followed the end
        self.dc.toggle_autoscroll()
        self.assertFalse(self.dc.autoscroll_var.get())
        self.assertEqual(self.dc.pause_btn["text"], "RESUME SCROLL")
        self.dc.console.yview_moveto(0.0)
        for i in range(20):
            d.add(f"later {i}", "SYS")
        self.dc.pump()
        self._settle()
        self.assertEqual(self.dc.console.yview()[0], 0.0)             # view stayed put
        self.dc.toggle_autoscroll()
        self.assertTrue(self.dc.autoscroll_var.get())
        self.dc.clear_log()
        self.assertNotIn("row 5", self._text())
        self.assertEqual(self.dc.match_lbl["text"], "0 lines")
        d.add("after clear", "SYS")
        self.dc.pump()
        self.assertIn("after clear", self._text())
        self.assertNotIn("row 5", self._text())
        self.assertIn("row 5", "\n".join(d.last_lines(1000)))         # the report still has it

    def test_engine_cards_change_with_telemetry(self):
        self._select(1)
        before = {k: v.get() for k, v in self.dc.card_vars.items()}
        self.assertTrue(before["state"].startswith("IDLE"))
        eng = self.app.engine
        eng.telemetry.record(0.0, 0.002, 128, 48000, status=None)
        eng.telemetry.xruns = 4
        eng.peak_l, eng.peak_r, eng.input_peak = 0.5, 0.25, 0.125
        eng.is_active = True
        try:
            self.tab.on_tick()
            after = {k: v.get() for k, v in self.dc.card_vars.items()}
        finally:
            eng.is_active = False
        self.assertNotEqual(before["cpu"], after["cpu"])
        self.assertIn("4 card", after["drops"])
        self.assertTrue(after["peak"].startswith("0.50 / 0.25 / 0.1"))
        self.assertTrue(after["state"].startswith("MOUNTED"))
        self.assertEqual(after["blocks"], "1")

    def test_tables_sort_by_clicked_column(self):
        rows = [{"id": i, "driver": "WASAPI", "max_in": 1, "max_out": 2, "default_sr": 48000.0,
                 "name": n} for i, n in ((10, "Bravo"), (2, "Alpha"), (33, "Charlie"))]
        self.app._device_rows = rows
        self._select(2)
        self.dc.refresh()
        tv = self.dc.dev_tree
        ids = lambda: [tv.item(k, "values")[0] for k in tv.get_children()]
        self.assertEqual(ids(), ["10", "2", "33"])
        self.dc.sort_by(tv, "ID")
        self.assertEqual(ids(), ["2", "10", "33"])                    # numeric, not text order
        self.dc.sort_by(tv, "ID")
        self.assertEqual(ids(), ["33", "10", "2"])
        self.dc.refresh()                                             # sort survives the 500 ms refresh
        self.assertEqual(ids(), ["33", "10", "2"])
        self.assertIn("\u25BC", tv.heading("ID", "text"))
        self.dc.sort_by(tv, "Name")
        names = [tv.item(k, "values")[5] for k in tv.get_children()]
        self.assertEqual(names, ["Alpha", "Bravo", "Charlie"])
        # heading click goes through the same path
        self.app.add_empty_track()
        self.app.add_empty_track()
        self._select(3)
        self.dc.refresh()
        self.dc.sort_by(self.dc.track_tree, "Track")
        self.assertEqual(len(self.dc.track_tree.get_children()), 2)

    def test_load_graph_draws_100_percent_line(self):
        self._select(4)
        c = self.dc.load_canvas
        eng = self.app.engine
        for i in range(30):
            eng.telemetry.record(0.0, 0.001 * (1 + i % 5), 128, 48000, status=None)
        self.dc.draw_load()
        reds = [i for i in c.find_all() if c.type(i) == "line" and c.itemcget(i, "fill") == "#FF3333"]
        self.assertTrue(reds)
        texts = [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]
        self.assertIn("100 %", texts)
        self.assertGreater(len([i for i in c.find_all() if c.type(i) == "rectangle"]), 20)
        self.assertIn("late blocks", self.dc.load_lbl["text"])

    def test_report_preview_shows_report_text(self):
        self.app.dlog.add("marker for report", "SYS")
        self._select(5)
        shown = self.dc.report_text.get("1.0", "end")
        self.assertIn("== ENGINE ==", shown)
        self.assertIn("DEBUG REPORT", shown)
        self.assertIn("marker for report", shown)
        copied = self.dc.copy_report()
        self.assertIn("== ENGINE ==", copied)
        self.assertIn("== ENGINE ==", self.root.clipboard_get())

    def test_f12_and_shortcuts_still_work(self):
        self.root.focus_force()
        self.app.select_tab("tracks")
        self._settle()
        self.root.event_generate("<F12>")
        self._settle()
        self.assertEqual(self.app.current_tab_name(), "debug")
        self.assertTrue(self.dc.test_bar.winfo_manager())
        self.root.event_generate("<F12>")
        self._settle()
        self.assertFalse(self.dc.test_bar.winfo_manager())

    def test_buttons_use_the_theme(self):
        def walk(w):
            for c in w.winfo_children():
                yield c
                yield from walk(c)
        for b in [w for w in walk(self.dc) if w.winfo_class() == "TButton"]:
            self.assertTrue(str(b.cget("style")).endswith(".TButton") and str(b.cget("style")) != "TButton", str(b))


if __name__ == "__main__":
    unittest.main()
