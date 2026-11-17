"""Phase 9 / T008: theme, scalable fonts, ScrollableFrame, screenshot helper.
Needs Tk and a display (sandbox: xvfb-run -a python3 -m unittest ...); skipped otherwise."""
import os
import sys
import tempfile
import unittest

from tests import _stubs  # noqa: F401

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
    _r = tk.Tk()
    _r.destroy()
    HAVE_TK = True
except Exception:       # no tkinter or no display
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class UiFoundationTests(unittest.TestCase):
    def setUp(self):
        import ui_theme
        self.theme = ui_theme
        self.root = tk.Tk()
        self.root.geometry("320x220+0+0")
        ui_theme.set_scale(1.0)
        ui_theme.apply_theme(self.root)

    def tearDown(self):
        self.theme.set_scale(1.0)
        self.root.destroy()

    # ---------------------------------------------------------- helpers
    def _make_frame(self, body_h, body_w=100, **kw):
        from scroll_frame import ScrollableFrame
        sf = ScrollableFrame(self.root, **kw)
        sf.pack(fill="both", expand=True)
        inner = tk.Frame(sf.body, width=body_w, height=body_h, bg="#444444")
        inner.pack_propagate(False)
        inner.pack(anchor="nw")
        self._settle()
        return sf

    def _settle(self):
        for _ in range(4):
            self.root.update_idletasks()
            self.root.update()

    def _point_into(self, widget):
        self.root.event_generate("<Motion>", warp=True,
                                 x=widget.winfo_rootx() - self.root.winfo_rootx() + 20,
                                 y=widget.winfo_rooty() - self.root.winfo_rooty() + 20)
        self._settle()

    # ---------------------------------------------------- (1) scroll frame
    def test_tall_body_shows_vertical_scrollbar_short_hides_all(self):
        tall = self._make_frame(900)
        self.assertTrue(tall.vertical_visible)
        self.assertTrue(tall.vsb.winfo_ismapped())
        tall.destroy()
        short = self._make_frame(60, horizontal=True)
        self.assertFalse(short.vertical_visible)
        self.assertFalse(short.horizontal_visible)
        self.assertFalse(short.vsb.winfo_ismapped())
        self.assertFalse(short.hsb.winfo_ismapped())

    def test_scrollbar_hides_again_when_content_shrinks(self):
        sf = self._make_frame(900)
        self.assertTrue(sf.vertical_visible)
        for child in sf.body.winfo_children():
            child.configure(height=40)
        self._settle()
        self.assertFalse(sf.vertical_visible)
        self.assertEqual(sf.canvas.yview()[0], 0.0)

    def test_mouse_wheel_scrolls_vertically(self):
        sf = self._make_frame(900)
        self._point_into(sf.canvas)
        self.assertEqual(sf.canvas.yview()[0], 0.0)
        for _ in range(3):
            sf.canvas.event_generate("<MouseWheel>", delta=-120)       # Windows style, down
        self._settle()
        after_down = sf.canvas.yview()[0]
        self.assertGreater(after_down, 0.0)
        sf.canvas.event_generate("<MouseWheel>", delta=120)            # up
        self._settle()
        self.assertLess(sf.canvas.yview()[0], after_down)

    def test_button4_button5_scroll_vertically(self):
        sf = self._make_frame(900)
        self._point_into(sf.canvas)
        sf.canvas.event_generate("<Button-5>")                         # X11 down
        sf.canvas.event_generate("<Button-5>")
        self._settle()
        pos = sf.canvas.yview()[0]
        self.assertGreater(pos, 0.0)
        sf.canvas.event_generate("<Button-4>")                         # X11 up
        self._settle()
        self.assertLess(sf.canvas.yview()[0], pos)

    def test_shift_wheel_scrolls_horizontally(self):
        sf = self._make_frame(60, body_w=900, vertical=False, horizontal=True)
        self.assertTrue(sf.horizontal_visible)
        self._point_into(sf.canvas)
        self.assertEqual(sf.canvas.xview()[0], 0.0)
        sf.canvas.event_generate("<Shift-MouseWheel>", delta=-120)
        sf.canvas.event_generate("<Shift-MouseWheel>", delta=-120)
        self._settle()
        self.assertGreater(sf.canvas.xview()[0], 0.0)
        self.assertEqual(sf.canvas.yview()[0], 0.0)

    def test_wheel_ignored_when_pointer_outside(self):
        from scroll_frame import ScrollableFrame
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        header = tk.Label(outer, text="header", height=3)
        header.grid(row=0, column=0, sticky="ew")
        sf = ScrollableFrame(outer)
        sf.grid(row=1, column=0, sticky="nsew")
        tk.Frame(sf.body, width=100, height=900).pack(anchor="nw")
        self._settle()
        self._point_into(header)               # pointer is NOT over the scroll frame
        sf.canvas.event_generate("<MouseWheel>", delta=-120)
        self._settle()
        self.assertEqual(sf.canvas.yview()[0], 0.0)

    def test_wheel_event_with_string_widget_does_not_raise(self):
        """T029: Tk gives event.widget as a plain str for widgets it has no Python
        object for (e.g. a drop-down list). The global handler must not raise."""
        import types
        import scroll_frame
        sf = self._make_frame(900)
        self._point_into(sf.canvas)
        ev = types.SimpleNamespace(widget=".!combobox.popdown.f.l", num=5, delta=0, state=0)
        res = scroll_frame._on_global_wheel(ev)       # used to raise AttributeError
        self._settle()
        self.assertEqual(res, "break")                 # pointer is over the frame: it scrolls
        self.assertGreater(sf.canvas.yview()[0], 0.0)
        # and with no usable widget at all, it just ignores the event
        ev2 = types.SimpleNamespace(widget="", num=4, delta=0, state=0)
        scroll_frame._on_global_wheel(ev2)

    def test_scroll_to_brings_widget_into_view(self):
        from scroll_frame import ScrollableFrame
        sf = ScrollableFrame(self.root)
        sf.pack(fill="both", expand=True)
        tk.Frame(sf.body, width=100, height=700).pack(anchor="nw")
        target = tk.Label(sf.body, text="target", height=2)
        target.pack(anchor="nw")
        self._settle()
        view_h = sf.canvas.winfo_height()
        self.assertGreater(target.winfo_y(), view_h)        # starts off-screen
        sf.scroll_to(target)
        self._settle()
        top = target.winfo_rooty() - sf.canvas.winfo_rooty()
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(top + target.winfo_height(), view_h + 1)

    def test_bind_wheel_normalises_direction(self):
        from scroll_frame import bind_wheel
        seen = []
        w = tk.Frame(self.root, width=50, height=50)
        w.pack()
        bind_wheel(w, lambda d, e: seen.append(d))
        self._settle()
        w.event_generate("<MouseWheel>", delta=-120)
        w.event_generate("<MouseWheel>", delta=120)
        w.event_generate("<Button-4>")
        w.event_generate("<Button-5>")
        self._settle()
        self.assertEqual(seen, [-1, 1, 1, -1])

    # ------------------------------------------------------- (2) scaling
    def test_set_scale_changes_fonts_and_row_height(self):
        th = self.theme
        style = ttk.Style(self.root)
        size0 = tkfont.nametofont(th.font("UI"), root=self.root).cget("size")
        title0 = tkfont.nametofont(th.font("TITLE"), root=self.root).cget("size")
        row0 = int(style.lookup("Treeview", "rowheight"))
        got = th.set_scale(1.5)
        self.assertEqual(got, 1.5)
        self.assertEqual(tkfont.nametofont(th.font("UI"), root=self.root).cget("size"), round(size0 * 1.5))
        self.assertGreater(tkfont.nametofont(th.font("TITLE"), root=self.root).cget("size"), title0)
        self.assertEqual(int(style.lookup("Treeview", "rowheight")), round(row0 * 1.5))
        self.assertEqual(th.scaled(10), 15)

    def test_set_scale_clamps(self):
        th = self.theme
        self.assertEqual(th.set_scale(5), 2.0)
        self.assertEqual(th.get_scale(), 2.0)
        self.assertEqual(th.set_scale(0.1), 0.8)
        self.assertEqual(th.get_scale(), 0.8)
        self.assertEqual(th.set_scale("junk"), 1.0)

    def test_scale_listeners_called_and_isolated(self):
        th = self.theme
        got = []
        def bad(_s):
            raise RuntimeError("boom")
        th.add_scale_listener(bad)
        th.add_scale_listener(got.append)
        try:
            th.set_scale(1.25)
        finally:
            th.remove_scale_listener(bad)
            th.remove_scale_listener(got.append)
        self.assertEqual(got, [1.25])

    # --------------------------------------------------------- (3) theme
    def test_apply_theme_twice_and_palette(self):
        th = self.theme
        th.apply_theme(self.root)
        th.apply_theme(self.root)
        p = th.PALETTE
        self.assertEqual(p["bg"], "#121212")
        self.assertEqual(p["surface1"], "#1E1E1E")
        self.assertEqual(p["accent"], "#00FF66")
        self.assertEqual(p["record"], "#FF3333")
        self.assertEqual(p["fx"], "#B266FF")
        style = ttk.Style(self.root)
        self.assertEqual(style.lookup("Action.TButton", "background"), "#00FF66")
        for key in th.FONT_NAMES:
            tkfont.nametofont(th.font(key), root=self.root)      # all named fonts exist

    def test_widgets_build_with_every_style(self):
        for cls, style in ((ttk.Button, "Action.TButton"), (ttk.Button, "Stop.TButton"),
                           (ttk.Button, "Fx.TButton"), (ttk.Button, "Neutral.TButton"),
                           (ttk.Combobox, "TCombobox"), (ttk.Scale, "Horizontal.TScale"),
                           (ttk.Treeview, "Treeview"), (ttk.Notebook, "TNotebook")):
            w = cls(self.root, style=style)
            w.pack()
        self._settle()


@unittest.skipUnless(HAVE_TK, "Tk or display not available")
class ScreenshotHelperTests(unittest.TestCase):
    def test_snap_writes_png(self):
        import shutil
        try:
            from PIL import ImageGrab  # noqa: F401
            have_pil = True
        except Exception:
            have_pil = False
        if not (shutil.which("import") or have_pil):
            self.skipTest("neither ImageMagick nor Pillow available")
        from tools.gui_shot import snap
        root = tk.Tk()
        try:
            root.geometry("200x120+0+0")
            tk.Label(root, text="shot", bg="#00FF66").pack(fill="both", expand=True)
            with tempfile.TemporaryDirectory() as d:
                out = snap(root, os.path.join(d, "sub", "s.png"))
                self.assertTrue(os.path.exists(out))
                with open(out, "rb") as f:
                    self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
