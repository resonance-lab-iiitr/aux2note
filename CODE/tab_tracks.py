"""
tab_tracks.py  (Phase 9 / T011)
The Tracks tab: a full-screen editing workspace. tabs.load_tab("tracks", ...) picks the
class `Tab` below instead of the old tabs.TracksTab; app.py and tabs.py are not edited.

What it adds over the old tab
    * zoom:  toolbar ZOOM - / ZOOM + / FIT, Ctrl+wheel zooms about the mouse pointer,
             the View menu items "Timeline zoom in/out" (app.view.zoom) zoom about the centre
    * rows:  ROWS - / ROWS + change the row height of every track (T009 height levels)
    * scroll: wheel = up/down, Shift+wheel = sideways, scrollbar; the ruler always follows
    * follow playhead: the view scrolls only when the playhead leaves it, and only while the
             playhead is moving (so you can scroll away freely while stopped)
    * + TRACK button inside the tab, a playhead line over every waveform
    * the timeline has no width limit: horizontal scrolling is virtual. Every canvas is only
      as wide as the window and draws just the part that is on screen (waveform_widget,
      viewport mode), so deep zoom on a long clip stays fast.

Public interface kept from tabs.TracksTab (app.py relies on it): add_track_strip, remove_track_strip,
rebuild_all, refresh_states, redraw_all, set_playhead, redraw_recording, view, ruler,
track_strips, empty_state_lbl. `view` is a timeline_view.TimelineView whose zoom(factor)
zooms about the centre of the window.
"""
import tkinter as tk
from tkinter import ttk

import ui_theme as theme
from scroll_frame import bind_wheel
from tabs import BaseTab
from timeline_view import TimelineView
from waveform_widget import (TimelineRuler, TrackStrip, CONTROL_COL_WIDTH, NUDGE_SEC, NUDGE_FINE_SEC,
                             nudge_offset, format_offset, control_col_width, ruler_height)

ZOOM_STEP = 1.25
MIN_EXTENT_SEC = 20.0        # the timeline is at least this long
EXTRA_TAIL_SEC = 10.0        # empty time kept after the last clip / the playhead
FALLBACK_VIEWPORT_PX = 900   # window width used before the tab is on screen
_CTRL, _SHIFT = 0x4, 0x1
NUDGE_READOUT_MS = 900       # how long the offset readout stays after an arrow-key nudge
# Widgets that use the arrow keys themselves: the clip nudge must leave them alone.
_ARROW_OWNERS = {"Entry", "TEntry", "Text", "Spinbox", "TSpinbox", "TCombobox", "Scale", "TScale",
                 "Listbox", "Treeview", "TNotebook", "Scrollbar", "TScrollbar"}


class _TabView(TimelineView):
    """TimelineView whose zoom(factor) zooms about the middle of the window (the tab sets
    zoom_hook). Without a hook it behaves like the base class."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.zoom_hook = None

    def zoom(self, factor):
        if self.zoom_hook is not None:
            self.zoom_hook(factor)
            return self.px_per_sec
        return super().zoom(factor)


class Tab(BaseTab):
    title = "Tracks"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.engine = app.engine
        self.view = _TabView(px_per_sec=80.0)
        self.view.zoom_hook = self._zoom_center
        self.view.add_listener(self._on_view_changed)      # first listener: runs before the strips'
        self.track_strips = {}
        self.scroll_px = 0.0                               # timeline pixel at the left edge of the window
        self._pending_scroll = None                        # new scroll offset to apply with a zoom
        self._playhead_sec = 0.0
        self._last_follow_sec = None
        self._extent_sec = MIN_EXTENT_SEC
        self.follow_var = tk.BooleanVar(value=True)
        self.selected_track_id = None                      # selected clip: view state, never saved
        self._readout_job = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_hint_banner()
        self._build_toolbar()
        self._build_timeline_area()
        self._update_labels()
        self.bind("<Destroy>", self._on_destroy, add="+")
        theme.add_scale_listener(self._on_scale)           # T016: fixed pixel sizes follow the UI scale
        self.winfo_toplevel().bind("<Left>", self._on_arrow, add="+")
        self.winfo_toplevel().bind("<Right>", self._on_arrow, add="+")

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #
    def _build_hint_banner(self):
        p = theme.PALETTE
        self.hint_frame = tk.Frame(self, bg=p["hint_bg"])
        self.hint_frame.grid(row=0, column=0, sticky="ew")
        self.hint_frame.columnconfigure(0, weight=1)
        text = ("Quick start:  1) Audio tab: pick an Input + Output device  \u2192  "
                "2) MOUNT AUDIO ENGINE  \u2192  3) + TRACK  \u2192  "
                "4) tick ARM on that track  \u2192  5) RECORD ARMED to capture audio.")
        self.hint_lbl = tk.Label(self.hint_frame, text=text, bg=p["hint_bg"], fg=p["hint_fg"],
                                 font=theme.font("SMALL"), anchor="w", justify="left", wraplength=1000)
        self.hint_lbl.grid(row=0, column=0, sticky="ew", padx=12, pady=6)
        ttk.Button(self.hint_frame, text="Got it", style="Neutral.TButton", takefocus=False,
                   command=self.hint_frame.grid_remove).grid(row=0, column=1, padx=10, pady=6)
        self.hint_frame.bind("<Configure>",
                             lambda e: self.hint_lbl.configure(wraplength=max(200, e.width - 140)))

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(8, 4))
        bar.grid(row=1, column=0, sticky="ew")
        self.toolbar = bar

        def button(text, command, width=None):
            b = ttk.Button(bar, text=text, style="Neutral.TButton", takefocus=False, command=command)
            if width:
                b.configure(width=width)
            b.pack(side="left", padx=2)
            return b

        self.add_btn = button("+ TRACK", self.app.add_empty_track)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        self.zoom_out_btn = button("ZOOM -", lambda: self._zoom_center(1.0 / ZOOM_STEP), 7)
        self.zoom_in_btn = button("ZOOM +", lambda: self._zoom_center(ZOOM_STEP), 7)
        self.fit_btn = button("FIT", self.fit, 5)
        self.zoom_lbl = ttk.Label(bar, text="", width=8)
        self.zoom_lbl.pack(side="left", padx=6)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        self.rows_down_btn = button("ROWS -", self.view.height_down, 7)
        self.rows_up_btn = button("ROWS +", self.view.height_up, 7)
        self.rows_lbl = ttk.Label(bar, text="", width=7)
        self.rows_lbl.pack(side="left", padx=6)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        self.follow_chk = ttk.Checkbutton(bar, text="Follow playhead", variable=self.follow_var,
                                          takefocus=False)
        self.follow_chk.pack(side="left", padx=4)
        self.wheel_hint = ttk.Label(bar, text="Ctrl+wheel: zoom", foreground=theme.PALETTE["muted"])
        self._layout_toolbar_hint()

    def _layout_toolbar_hint(self):
        """The 'Ctrl+wheel' hint is dropped from 130 percent up: the buttons need the room."""
        if theme.get_scale() >= 1.3:
            self.wheel_hint.pack_forget()
        elif not self.wheel_hint.winfo_manager():
            self.wheel_hint.pack(side="right", padx=6)

    def _build_timeline_area(self):
        p = theme.PALETTE
        outer = ttk.Frame(self, padding=(6, 0, 6, 6))
        outer.grid(row=2, column=0, sticky="nsew")
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(1, weight=1)
        self.outer = outer

        self.ruler_spacer = tk.Frame(outer, width=control_col_width(), height=ruler_height(), bg=p["bg"])
        self.ruler_spacer.grid(row=0, column=0, sticky="nsew")
        self.ruler = TimelineRuler(outer, self.view, self.engine.sample_rate,
                                   width_px=FALLBACK_VIEWPORT_PX, virtual=True)
        self.ruler.grid(row=0, column=1, sticky="ew")
        self.ruler.bind("<Button-1>", self._on_ruler_click)
        self.ruler.bind("<B1-Motion>", self._on_ruler_click)

        self.header_canvas = tk.Canvas(outer, width=control_col_width(), bg=p["bg"], highlightthickness=0,
                                       yscrollincrement=theme.scaled(30))
        self.header_canvas.grid(row=1, column=0, sticky="ns")
        self.header_frame = tk.Frame(self.header_canvas, bg=p["bg"])
        self.header_canvas.create_window((0, 0), window=self.header_frame, anchor="nw")

        self.tracks_canvas = tk.Canvas(outer, bg=p["bg"], highlightthickness=0,
                                       yscrollincrement=theme.scaled(30))
        self.tracks_canvas.grid(row=1, column=1, sticky="nsew")
        self.tracks_frame = tk.Frame(self.tracks_canvas, bg=p["bg"])
        self._tracks_win = self.tracks_canvas.create_window((0, 0), window=self.tracks_frame, anchor="nw")
        self.tracks_canvas.bind("<Configure>", self._on_canvas_configure)
        self.tracks_frame.bind("<Configure>", self._on_frames_configure)
        self.header_frame.bind("<Configure>", self._on_frames_configure)

        self.empty_state_lbl = tk.Label(
            self.tracks_frame, bg=p["bg"], fg="#555555", font=theme.font("UI"),
            text="No tracks yet - click '+ TRACK' or 'IMPORT' above to get started.")
        self.empty_state_lbl.pack(pady=40)

        self.vscroll = ttk.Scrollbar(outer, orient="vertical", command=self._on_vscroll)
        self.vscroll.grid(row=1, column=2, sticky="ns")
        self.hscroll = ttk.Scrollbar(outer, orient="horizontal", command=self._on_hscroll)
        self.hscroll.grid(row=2, column=1, sticky="ew")
        self.tracks_canvas.configure(yscrollcommand=lambda a, b: self.vscroll.set(a, b))

        for widget in (self.header_canvas, self.tracks_canvas, self.header_frame, self.tracks_frame,
                       self.empty_state_lbl, self.ruler):
            self._bind_wheel_tree(widget)

    # ------------------------------------------------------------------ #
    # Geometry helpers
    # ------------------------------------------------------------------ #
    def viewport_px(self):
        w = self.tracks_canvas.winfo_width()
        return float(w if w > 1 else FALLBACK_VIEWPORT_PX)

    def clip_range_sec(self):
        """End of the last clip in seconds (0 when every track is empty)."""
        ends = [t.end_offset / float(t.sample_rate) for t in self.engine.tracks if t.length > 0]
        return max(ends, default=0.0)

    def _compute_extent_sec(self):
        return max(MIN_EXTENT_SEC, self.clip_range_sec() + EXTRA_TAIL_SEC, self._playhead_sec + EXTRA_TAIL_SEC)

    def content_width_px(self):
        return max(self.viewport_px(), self.view.sec_to_px(self._extent_sec))

    def max_scroll_px(self):
        return max(0.0, self.content_width_px() - self.viewport_px())

    def _set_scroll_quiet(self, px):
        """Store the scroll offset everywhere without redrawing. Returns the clamped value."""
        px = max(0.0, min(float(px), self.max_scroll_px()))
        self.scroll_px = px
        self.ruler.scroll_px = px
        for strip in self.track_strips.values():
            strip.waveform.scroll_px = px
        return px

    def _update_hscroll(self):
        cw, vp = self.content_width_px(), self.viewport_px()
        self.hscroll.set(self.scroll_px / cw, min(1.0, (self.scroll_px + vp) / cw))

    def _update_labels(self):
        self.zoom_lbl.configure(text=f"{self.view.px_per_sec:.0f} px/s")
        self.rows_lbl.configure(text=f"row {self.view.track_height}")

    # ------------------------------------------------------------------ #
    # Scrolling
    # ------------------------------------------------------------------ #
    def scroll_to_px(self, px, force=False):
        """Scroll the timeline so pixel `px` is at the left edge. Redraws ruler and waveforms."""
        old = self.scroll_px
        new = self._set_scroll_quiet(px)
        if force or abs(new - old) >= 0.5:
            self.ruler.redraw()
            for strip in self.track_strips.values():
                strip.waveform.redraw()
        self._update_hscroll()
        return new

    def scroll_by(self, delta_px):
        return self.scroll_to_px(self.scroll_px + delta_px)

    def _on_hscroll(self, *args):
        vp = self.viewport_px()
        if args[0] == "moveto":
            self.scroll_to_px(float(args[1]) * self.content_width_px())
        elif args[0] == "scroll":
            n = int(args[1])
            self.scroll_by(n * (0.9 * vp if args[2] == "pages" else 40.0))

    def _on_vscroll(self, *args):
        self.header_canvas.yview(*args)
        self.tracks_canvas.yview(*args)

    def _bind_wheel_tree(self, widget):
        bind_wheel(widget, self._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel_tree(child)

    def _on_wheel(self, direction, event):
        state = event.state if isinstance(event.state, int) else 0
        if state & _CTRL:
            try:
                anchor = event.x_root - self.tracks_canvas.winfo_rootx()
            except (TypeError, tk.TclError):
                anchor = self.viewport_px() / 2
            anchor = max(0.0, min(float(anchor), self.viewport_px()))
            self.zoom_about(ZOOM_STEP if direction > 0 else 1.0 / ZOOM_STEP, anchor)
        elif state & _SHIFT:
            self.scroll_by(-direction * 0.2 * self.viewport_px())
        else:
            self.header_canvas.yview_scroll(-direction, "units")
            self.tracks_canvas.yview_scroll(-direction, "units")
        return "break"

    # ------------------------------------------------------------------ #
    # Zoom
    # ------------------------------------------------------------------ #
    def zoom_about(self, factor, anchor_x):
        """Zoom by `factor` keeping the time under window pixel `anchor_x` where it is."""
        probe = TimelineView(self.view.px_per_sec)
        new_scroll = probe.zoom_at(factor, anchor_x, self.scroll_px)
        self._pending_scroll = new_scroll
        try:
            self.view.set_px_per_sec(probe.px_per_sec)     # notifies: ruler + strips redraw once
        finally:
            self._pending_scroll = None
        return self.view.px_per_sec

    def _zoom_center(self, factor):
        return self.zoom_about(factor, self.viewport_px() / 2.0)

    def fit(self):
        """Zoom so every clip is visible (from time 0 to the end of the last clip)."""
        total = self.clip_range_sec()
        if total <= 0:
            return
        self._pending_scroll = 0.0
        try:
            self.view.fit(total, self.viewport_px())
        finally:
            self._pending_scroll = None
        self.scroll_to_px(0.0)

    def _on_view_changed(self):
        """View listener (zoom, fit, row height): re-measure the timeline and redraw the ruler.
        The strips redraw after this because they subscribe later."""
        if not hasattr(self, "ruler"):
            return
        pending, self._pending_scroll = self._pending_scroll, None
        self._extent_sec = self._compute_extent_sec()
        self._set_scroll_quiet(self.scroll_px if pending is None else pending)
        self.ruler.redraw()
        self._update_labels()
        self._update_hscroll()

    # ------------------------------------------------------------------ #
    # Geometry events
    # ------------------------------------------------------------------ #
    def _on_canvas_configure(self, event):
        self.tracks_canvas.itemconfigure(self._tracks_win, width=event.width)
        self._set_scroll_quiet(self.scroll_px)
        self._update_hscroll()
        self._on_frames_configure()

    def _on_frames_configure(self, _event=None):
        for canvas in (self.header_canvas, self.tracks_canvas):
            box = canvas.bbox("all")
            if box:
                canvas.configure(scrollregion=(0, 0, box[2], box[3]))

    def _on_ruler_click(self, event):
        sec = self.ruler.x_to_seconds(event.x)
        self.engine.set_playhead_seconds(sec)
        self.set_playhead(sec)

    # ------------------------------------------------------------------ #
    # Public interface used by app.py
    # ------------------------------------------------------------------ #
    def add_track_strip(self, track):
        self.empty_state_lbl.pack_forget()
        self.hint_frame.grid_remove()          # the quick-start hint is for the empty first run
        strip = TrackStrip(self.header_frame, self.tracks_frame, track, self.engine, self.view,
                           on_change=self.app._on_track_changed, on_remove=self.app.remove_track,
                           on_open_fx=lambda t: self.app.open_fx(t), width_px=int(self.viewport_px()),
                           virtual=True, on_select=self.select_track, snap_points=self.snap_points_for)
        strip.waveform.scroll_px = self.scroll_px
        strip.waveform.selected = (track.id == self.selected_track_id)
        strip.waveform.set_playhead_seconds(self._playhead_sec)
        strip.pack()
        self.track_strips[track.id] = strip
        self._bind_wheel_tree(strip.header)
        self._bind_wheel_tree(strip.waveform)
        self._remeasure()
        return strip

    def remove_track_strip(self, track):
        strip = self.track_strips.pop(track.id, None)
        if strip:
            strip.destroy()
        if self.selected_track_id == track.id:
            self.selected_track_id = None
        self._relayout()
        self._remeasure()

    def _relayout(self):
        for strip in self.track_strips.values():
            strip.header.pack_forget()
            strip.waveform.pack_forget()
        for track in self.engine.tracks:
            if track.id in self.track_strips:
                self.track_strips[track.id].pack()
        if not self.engine.tracks:
            self.empty_state_lbl.pack(pady=40)

    def rebuild_all(self):
        for strip in list(self.track_strips.values()):
            strip.destroy()
        self.track_strips = {}
        for track in self.engine.tracks:
            self.add_track_strip(track)
        if not self.engine.tracks:
            self.empty_state_lbl.pack(pady=40)
        self._remeasure()

    def refresh_states(self):
        for strip in self.track_strips.values():
            strip.sync_from_model()
            strip.redraw()
        self._remeasure()

    def redraw_all(self):
        for strip in self.track_strips.values():
            strip.redraw()
        self._remeasure()

    def _remeasure(self):
        """Clips may have changed: recompute the timeline length and keep the scroll valid."""
        self._extent_sec = self._compute_extent_sec()
        self._set_scroll_quiet(self.scroll_px)
        self._update_hscroll()

    def set_playhead(self, sec):
        self._playhead_sec = sec
        if sec + 5.0 > self._extent_sec:                 # playing past the end: grow the timeline
            self._extent_sec = self._compute_extent_sec()
            self._update_hscroll()
        self._follow(sec)
        self.ruler.set_playhead_seconds(sec)
        for strip in self.track_strips.values():
            strip.waveform.set_playhead_seconds(sec)

    def _follow(self, sec):
        """Scroll only when the playhead has moved AND is outside the window."""
        moved = self._last_follow_sec is None or abs(sec - self._last_follow_sec) > 1e-9
        self._last_follow_sec = sec
        if not (moved and self.follow_var.get()):
            return
        x, vp = self.view.sec_to_px(sec), self.viewport_px()
        if x < self.scroll_px or x > self.scroll_px + vp:
            self.scroll_to_px(x - 0.1 * vp)

    # ------------------------------------------------------------------ #
    # Clip editing aids (T015): selection, snapping, arrow-key nudge
    # ------------------------------------------------------------------ #
    def selected_track(self):
        for t in self.engine.tracks:
            if t.id == self.selected_track_id:
                return t
        return None

    def select_track(self, track):
        """Select one clip (or None to clear). Only one clip is selected at a time."""
        new_id = track.id if track is not None else None
        if new_id == self.selected_track_id:
            return
        self.selected_track_id = new_id
        for tid, strip in self.track_strips.items():
            strip.waveform.set_selected(tid == new_id)

    def snap_points_for(self, track):
        """Seconds a dragged clip snaps to: the start and end of every other clip."""
        pts = []
        for t in self.engine.tracks:
            if t is track or t.length == 0:
                continue
            pts.append(t.offset / float(t.sample_rate))
            pts.append(t.end_offset / float(t.sample_rate))
        return pts

    def _on_arrow(self, event):
        """Left / Right nudge the selected clip by 10 ms (Shift: 100 ms), never below 0."""
        widget = event.widget
        try:
            if widget.winfo_class() in _ARROW_OWNERS:
                return None                           # typing in a box / moving a slider: not ours
        except tk.TclError:
            return None
        track = self.selected_track()
        if track is None or track.recording or not self.winfo_ismapped():
            return None
        state = event.state if isinstance(event.state, int) else 0
        step = NUDGE_FINE_SEC if state & _SHIFT else NUDGE_SEC
        delta = int(round(step * track.sample_rate)) * (-1 if event.keysym == "Left" else 1)
        new = nudge_offset(track.offset, delta)
        if new != track.offset:
            track.offset = new
            self.app._on_track_changed()              # same call as a drag: loop end is recomputed
        self._flash_readout(track)
        return "break"

    def _flash_readout(self, track):
        strip = self.track_strips.get(track.id)
        if strip is None:
            return
        strip.waveform.show_readout(format_offset(track.offset, track.sample_rate))
        if self._readout_job is not None:
            try:
                self.after_cancel(self._readout_job)
            except tk.TclError:
                pass
        self._readout_job = self.after(NUDGE_READOUT_MS, self._clear_readouts)

    def _on_destroy(self, event):
        """Cancel the readout timer. A <Destroy> binding is used because destroying the root does
        not call destroy() on nested widgets, so an after job would fire into a dead tab."""
        if str(event.widget) == str(self):
            theme.remove_scale_listener(self._on_scale)
        if str(event.widget) == str(self) and self._readout_job is not None:
            try:
                self.after_cancel(self._readout_job)
            except tk.TclError:
                pass
            self._readout_job = None

    def _on_scale(self, scale):
        """UI scale changed (T016). Fonts and ttk styles already follow ui_theme; fix the pixel
        sizes: header column, ruler, row heights (view level x scale), wheel step, hint wrap."""
        try:
            self._layout_toolbar_hint()
            self.ruler_spacer.configure(width=control_col_width(), height=ruler_height())
            self.header_canvas.configure(width=control_col_width(),
                                         yscrollincrement=theme.scaled(30))
            self.tracks_canvas.configure(yscrollincrement=theme.scaled(30))
            self.ruler.rescale()
            for strip in self.track_strips.values():
                strip.rescale()
            self._on_frames_configure()
            self._update_labels()
            self.scroll_to_px(self.scroll_px, force=True)
        except tk.TclError:
            pass

    def _clear_readouts(self):
        self._readout_job = None
        for strip in self.track_strips.values():
            strip.waveform.show_readout(None)

    def redraw_recording(self):
        """Redraw only strips that are recording (the app calls this every 60 ms)."""
        for strip in self.track_strips.values():
            if strip.track.recording:
                strip.redraw()

    # ---- tab contract ---------------------------------------------------- #
    def on_show(self):
        self.redraw_all()
        self.ruler.redraw()

    def on_tick(self):
        pass
