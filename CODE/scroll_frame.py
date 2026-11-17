"""
scroll_frame.py
ScrollableFrame: a frame whose `.body` can be taller (and optionally wider)
than the window. Scrollbars appear only when the content does not fit.

    sf = ScrollableFrame(parent, vertical=True, horizontal=False)
    sf.pack(fill="both", expand=True)
    ttk.Label(sf.body, text="...").pack()

Mouse wheel scrolls the frame under the pointer (Windows MouseWheel and X11
Button-4/5); Shift+wheel scrolls sideways. Nested frames: the innermost frame
that can still scroll takes the event.

bind_wheel(widget, handler) gives a normalised wheel binding, e.g. for
Ctrl+wheel zoom: handler(direction, event) with direction +1 (wheel up)
or -1 (wheel down); check event.state & 0x4 for Ctrl, & 0x1 for Shift.
"""
import tkinter as tk
from tkinter import ttk

import ui_theme as theme

_SHIFT = 0x1
_STEP_PX = 24
_registry = {}       # str(frame path) -> ScrollableFrame (live frames)


def wheel_direction(event):
    """+1 for wheel up / away, -1 for wheel down / toward. 0 if unknown."""
    num = getattr(event, "num", None)
    if num == 4:
        return 1
    if num == 5:
        return -1
    delta = getattr(event, "delta", 0)
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def bind_wheel(widget, handler):
    """Bind handler(direction, event) to the wheel on `widget` (all platforms).
    The handler's return value is passed on, so return "break" to stop others."""
    def _cb(event):
        d = wheel_direction(event)
        if d:
            return handler(d, event)
        return None
    widget.bind("<MouseWheel>", _cb, add="+")
    widget.bind("<Button-4>", _cb, add="+")
    widget.bind("<Button-5>", _cb, add="+")


def _pointer_widget(widget, event):
    """Widget under the mouse pointer. Tk gives `event.widget` as a plain str when it
    has no Python object for the widget (e.g. a drop-down list), so fall back to the
    Tk root for the lookup (T029)."""
    host = widget if hasattr(widget, "winfo_containing") else getattr(tk, "_default_root", None)
    w = None
    if host is not None:
        try:
            w = host.winfo_containing(host.winfo_pointerx(), host.winfo_pointery())
        except (tk.TclError, KeyError, AttributeError):
            w = None
    if w is not None:
        return w
    ew = getattr(event, "widget", None)
    return None if isinstance(ew, str) else ew


def _on_global_wheel(event):
    d = wheel_direction(event)
    if not d:
        return None
    w = _pointer_widget(event.widget, event)
    shift = bool(event.state & _SHIFT) if isinstance(event.state, int) else False
    while w is not None:
        frame = _registry.get(str(w))
        if frame is not None and frame._scroll_wheel(d, shift):
            return "break"
        try:
            w = w.master
        except AttributeError:
            break
    return None


def _bind_global(root):
    top = root.winfo_toplevel()
    if getattr(top, "_ll_wheel_bound", False):
        return
    top._ll_wheel_bound = True
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        root.bind_all(seq, _on_global_wheel, add="+")


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, vertical=True, horizontal=False, **kw):
        super().__init__(parent, **kw)
        self.vertical = vertical
        self.horizontal = horizontal
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=theme.PALETTE["bg"], highlightthickness=0, bd=0,
                                yscrollincrement=theme.scaled(_STEP_PX),
                                xscrollincrement=theme.scaled(_STEP_PX))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self._vsb_shown = False
        self._hsb_shown = False

        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._relayout)
        self.canvas.bind("<Configure>", self._relayout)

        _registry[str(self)] = self
        self.bind("<Destroy>", self._on_destroy, add="+")
        _bind_global(self)
        theme.add_scale_listener(self._on_scale)

    # ------------------------------------------------------------ layout
    def _relayout(self, _event=None):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1 or ch <= 1:
            return
        rw, rh = self.body.winfo_reqwidth(), self.body.winfo_reqheight()
        # The body keeps its natural height (and natural width when horizontal scrolling is
        # on) so Tk keeps sending <Configure> when the content changes size. Without
        # horizontal scrolling it is stretched to the viewport width.
        if self.horizontal:
            bw = max(rw, cw)
            self.canvas.itemconfigure(self._win, width=0)
        else:
            bw = cw
            self.canvas.itemconfigure(self._win, width=cw)
        self.canvas.itemconfigure(self._win, height=0)
        bh = rh
        self.canvas.configure(scrollregion=(0, 0, bw, bh))

        # Decide which scrollbars are needed (each one takes room from the other axis).
        sbw = self.vsb.winfo_reqwidth() if self._vsb_shown else theme.scaled(10)
        sbh = self.hsb.winfo_reqheight() if self._hsb_shown else theme.scaled(10)
        total_w = cw + (sbw if self._vsb_shown else 0)
        total_h = ch + (sbh if self._hsb_shown else 0)
        need_v = self.vertical and rh > total_h
        need_h = self.horizontal and rw > total_w
        if need_v and self.horizontal:
            need_h = rw > total_w - sbw
        if need_h and self.vertical:
            need_v = rh > total_h - sbh
        self._show_bars(need_v, need_h)
        if not need_v:
            self.canvas.yview_moveto(0)
        if not need_h:
            self.canvas.xview_moveto(0)

    def _show_bars(self, need_v, need_h):
        if need_v and not self._vsb_shown:
            self.vsb.grid(row=0, column=1, sticky="ns")
        elif not need_v and self._vsb_shown:
            self.vsb.grid_remove()
        if need_h and not self._hsb_shown:
            self.hsb.grid(row=1, column=0, sticky="ew")
        elif not need_h and self._hsb_shown:
            self.hsb.grid_remove()
        self._vsb_shown, self._hsb_shown = need_v, need_h

    def _on_scale(self, _scale):
        try:
            self.canvas.configure(yscrollincrement=theme.scaled(_STEP_PX),
                                  xscrollincrement=theme.scaled(_STEP_PX))
            self._relayout()
        except tk.TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is self:
            _registry.pop(str(self), None)
            theme.remove_scale_listener(self._on_scale)

    # ------------------------------------------------------------ scrolling
    @property
    def vertical_visible(self):
        return self._vsb_shown

    @property
    def horizontal_visible(self):
        return self._hsb_shown

    def _scroll_wheel(self, direction, shift):
        """Scroll one step. True if this frame consumed the event."""
        step = -direction       # wheel up -> view moves up -> negative units
        if shift or not self._vsb_shown:
            if not self._hsb_shown:
                return False
            self.canvas.xview_scroll(step, "units")
            return True
        self.canvas.yview_scroll(step, "units")
        return True

    def scroll_to(self, widget):
        """Scroll the minimum amount that makes `widget` (inside .body) fully visible."""
        self.update_idletasks()
        bh = max(1, int(float(self.canvas.cget("scrollregion").split()[3]))) \
            if self.canvas.cget("scrollregion") else self.body.winfo_height()
        bw = max(1, int(float(self.canvas.cget("scrollregion").split()[2]))) \
            if self.canvas.cget("scrollregion") else self.body.winfo_width()
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        left = widget.winfo_rootx() - self.body.winfo_rootx()
        bottom, right = top + widget.winfo_height(), left + widget.winfo_width()
        if self._vsb_shown:
            view_top = self.canvas.canvasy(0)
            view_h = self.canvas.winfo_height()
            if top < view_top:
                self.canvas.yview_moveto(top / bh)
            elif bottom > view_top + view_h:
                self.canvas.yview_moveto((bottom - view_h) / bh)
        if self._hsb_shown:
            view_left = self.canvas.canvasx(0)
            view_w = self.canvas.winfo_width()
            if left < view_left:
                self.canvas.xview_moveto(left / bw)
            elif right > view_left + view_w:
                self.canvas.xview_moveto((right - view_w) / bw)
