"""
waveform_widget.py
The visual, audio-editor-style timeline: a ruler on top and one draggable
waveform "strip" per track underneath, all sharing the same pixels-per-second
scale so you can slide any track left/right with the mouse to line it up
against any other track.

Layout notes (production-UX fix):
  The per-track controls (name/arm/mute/solo/loop/FX/volume/pan) live in a
  FROZEN header column that only scrolls vertically. The waveform area
  scrolls both ways. Previously the controls were baked into the same
  horizontally-scrolling strip as the waveform, so scrolling right on a long
  arrangement scrolled the controls out of view along with it - you lost
  access to mute/solo/arm/FX for every track the moment you scrolled to see
  later material. TrackHeader (controls) and WaveformCanvas (draggable clip)
  are now two independent widgets kept in sync by the small TrackStrip
  manager below and by app.py, which places one in the frozen header panel
  and the other in the scrolling timeline panel.
"""

import tkinter as tk
from tkinter import ttk

import numpy as np

import ui_theme as theme


TRACK_ROW_HEIGHT = 96
SLIDER_THICKNESS = 8       # T028: VOL / PAN trough thickness at scale 1.0 (a default tk.Scale is ~19 px tall)
SLIDER_LENGTH = 18         # T028: slider knob length at scale 1.0
CONTROL_COL_WIDTH = 230
ROW_PAD_Y = 2
RULER_HEIGHT = 28          # px at scale 1.0


def _sc(px):
    """Pixels at the current UI scale (T016)."""
    return theme.scaled(px)


def _font(family, size, weight=None):
    """Font tuple whose point size follows the UI scale (identical to the old literal at 100 %)."""
    pts = max(6, int(round(size * theme.get_scale())))
    return (family, pts, weight) if weight else (family, pts)


def control_col_width():
    """Width of the frozen header column at the current UI scale."""
    return _sc(CONTROL_COL_WIDTH)


def ruler_height():
    return _sc(RULER_HEIGHT)


def row_height(view):
    """Track row height in px: the new timeline_view.TimelineView has `track_height`
    (T009 height levels); the old TimelineView here does not, so it stays 96."""
    return _sc(int(getattr(view, "track_height", TRACK_ROW_HEIGHT)))


def snap_px():
    """Snap distance in screen pixels at the current UI scale."""
    return SNAP_PX * theme.get_scale()


def visible_peaks(buffer, first_px, last_px, samples_per_px):
    """Min and max sample for each pixel column first_px .. last_px-1 of a clip whose
    pixel 0 is its first sample. Reads only the samples under those columns, so the cost
    follows the screen width, not the clip length (used by the viewport drawing mode)."""
    n = int(last_px) - int(first_px)
    if n <= 0 or len(buffer) == 0:
        return np.zeros(max(n, 0), dtype=np.float32), np.zeros(max(n, 0), dtype=np.float32)
    edges = np.floor(np.arange(int(first_px), int(last_px) + 1, dtype=np.float64)
                     * float(samples_per_px)).astype(np.int64)
    edges = np.clip(edges, 0, len(buffer))
    e0, e1 = int(edges[0]), int(edges[-1])
    if e1 <= e0:
        return np.zeros(n, dtype=np.float32), np.zeros(n, dtype=np.float32)
    seg = buffer[e0:e1]
    starts = np.minimum(edges[:-1] - e0, len(seg) - 1)
    return np.minimum.reduceat(seg, starts), np.maximum.reduceat(seg, starts)


# ---- clip editing maths (plain functions: no Tk, easy to test) -------------------- #
FINE_DRAG_DIVISOR = 10.0     # Shift+drag moves the clip this many times slower than the pointer
SNAP_PX = 8.0                # snap distance on screen, in pixels
NUDGE_SEC = 0.010            # Left / Right arrow
NUDGE_FINE_SEC = 0.100       # Shift + Left / Right arrow
_SHIFT_BIT, _ALT_BIT = 0x1, 0x8


def snap_offset_info(offset_sec, candidates_sec, threshold_sec, duration_sec=0.0):
    """Snap a clip to the closest candidate time. Both the clip start (offset_sec) and, when
    duration_sec > 0, the clip end (offset_sec + duration_sec) are tried. Returns
    (new_offset_sec, target_sec); target_sec is None when nothing was within the threshold.
    The result is never negative."""
    best_delta, best_target = None, None
    for cand in candidates_sec:
        for edge in ((0.0, float(duration_sec)) if duration_sec > 0 else (0.0,)):
            delta = float(cand) - (offset_sec + edge)
            if abs(delta) <= threshold_sec and (best_delta is None or abs(delta) < abs(best_delta)):
                best_delta, best_target = delta, float(cand)
    if best_delta is None:
        return max(0.0, offset_sec), None
    new = offset_sec + best_delta
    if new < 0:
        return max(0.0, offset_sec), None
    return new, best_target


def snap_offset(offset_sec, candidates_sec, threshold_sec, duration_sec=0.0):
    """Like snap_offset_info but returns only the new offset in seconds."""
    return snap_offset_info(offset_sec, candidates_sec, threshold_sec, duration_sec)[0]


def drag_offset(start_offset, dx_px, px_per_sec, sample_rate, fine=False):
    """New clip offset in samples after the pointer moved dx_px from where the drag started.
    fine=True moves the clip FINE_DRAG_DIVISOR times slower. Never negative."""
    dx_sec = dx_px / float(px_per_sec)
    if fine:
        dx_sec /= FINE_DRAG_DIVISOR
    return max(0, int(start_offset + dx_sec * sample_rate))


def nudge_offset(offset, delta_samples):
    """Offset in samples after a nudge; never below 0."""
    return max(0, int(offset) + int(delta_samples))


def format_offset(offset_samples, sample_rate):
    """Readout text for a clip start, seconds and milliseconds, e.g. '1.500 s  (1500 ms)'."""
    sec = offset_samples / float(sample_rate)
    return f"{sec:.3f} s  ({int(round(sec * 1000.0))} ms)"


class TimelineView:
    """Shared horizontal scale (pixels-per-second) + scroll offset used by the
    ruler and every track strip so they all stay in sync."""

    def __init__(self, px_per_sec=80.0):
        self.px_per_sec = px_per_sec
        self.listeners = []

    def sec_to_px(self, sec):
        return sec * self.px_per_sec

    def px_to_sec(self, px):
        return px / self.px_per_sec

    def zoom(self, factor):
        self.px_per_sec = max(10.0, min(2000.0, self.px_per_sec * factor))
        self._notify()

    def add_listener(self, fn):
        self.listeners.append(fn)

    def _notify(self):
        for fn in self.listeners:
            fn()


class TimelineRuler(tk.Canvas):
    """The time ruler above the waveform area.

    Old mode (virtual=False, used by tabs.TracksTab): a scrollable canvas whose
    scrollregion is the full arrangement width, kept in step with the waveform area via
    xview. Without a configured scrollregion xview() is a silent no-op and the ruler stops
    tracking the visible window the moment you scroll right.

    Viewport mode (virtual=True, used by tab_tracks): the ruler is only as wide as the
    window and draws the ticks of the new timeline_view.TimelineView for the part of the
    timeline that starts at `scroll_px`. The tab changes `scroll_px` through
    set_scroll_px(); there is no scrollregion and no width limit."""

    def __init__(self, master, view, sample_rate, width_px=2400, virtual=False, **kw):
        super().__init__(master, height=ruler_height(), bg="#0A0A0A", highlightthickness=0, **kw)
        self.h = ruler_height()      # ruler height in px at the current UI scale (T016)
        self.view = view
        self.sample_rate = sample_rate
        self.width_px = width_px
        self.virtual = bool(virtual) and hasattr(view, "ticks")
        self.scroll_px = 0.0
        self._playhead_sec = 0.0
        self._last_size = None
        self.playhead_line = None
        if self.virtual:
            self.bind("<Configure>", self._on_configure)
        else:
            self.configure(scrollregion=(0, 0, self.width_px, self.h))
        self.redraw()

    def rescale(self):
        """UI scale changed: new height and fonts."""
        self.h = ruler_height()
        self.configure(height=self.h)
        self.redraw()

    def set_width_px(self, width_px):
        self.width_px = width_px
        if not self.virtual:
            self.configure(scrollregion=(0, 0, self.width_px, self.h))
        self.redraw()

    def set_scroll_px(self, px, redraw=True):
        self.scroll_px = max(0.0, float(px))
        if redraw:
            self.redraw()

    def _on_configure(self, event):
        if (event.width, event.height) != self._last_size:
            self._last_size = (event.width, event.height)
            self.redraw()

    def _viewport_w(self):
        w = self.winfo_width()
        return w if w > 1 else self.width_px

    def redraw(self):
        if self.virtual:
            self._redraw_viewport()
            return
        self.delete("all")
        px_per_sec = self.view.px_per_sec
        total_sec = self.width_px / px_per_sec
        step = 1
        if px_per_sec < 40:
            step = 5
        if px_per_sec < 15:
            step = 15
        t = 0
        while t <= total_sec:
            x = self.view.sec_to_px(t)
            self.create_line(x, 0, x, self.h, fill="#333333")
            self.create_text(x + 3, 4, anchor="nw", fill="#888888", font=_font("Consolas", 8),
                              text=f"{int(t // 60):02d}:{int(t % 60):02d}")
            t += step
        self.configure(scrollregion=(0, 0, self.width_px, self.h))
        self.playhead_line = self.create_line(0, 0, 0, self.h, fill="#FF3333", width=2)

    def _redraw_viewport(self):
        self.delete("all")
        w = self._viewport_w()
        scroll = self.scroll_px
        for tick in self.view.ticks(w, scroll):
            x = tick.x - scroll
            if x < -90 or x > w + 2:
                continue
            self.create_line(x, 0 if tick.major else _sc(10), x, self.h,
                             fill="#555555" if tick.major else "#333333", tags="tick")
            self.create_text(x + 3, 3, anchor="nw", fill="#B0B0B0" if tick.major else "#888888",
                             font=_font("Consolas", 8), text=tick.label, tags="label")
        self.playhead_line = self.create_line(0, 0, 0, self.h, fill="#FF3333", width=2, tags="playhead")
        self.set_playhead_seconds(self._playhead_sec)

    def set_playhead_seconds(self, sec):
        self._playhead_sec = sec
        x = self.view.sec_to_px(sec) - (self.scroll_px if self.virtual else 0.0)
        self.coords(self.playhead_line, x, 0, x, self.h)

    def x_to_seconds(self, event_x):
        """Convert a click's widget-local x to an absolute timeline second,
        accounting for however far the ruler is currently scrolled."""
        if self.virtual:
            return max(0.0, self.view.px_to_sec(self.scroll_px + event_x))
        frac = self.xview()[0]
        abs_x = frac * self.width_px + event_x
        return max(0.0, self.view.px_to_sec(abs_x))


class TrackHeader(ttk.Frame):
    """The frozen left-hand control column for one track: name, arm/mute/
    solo/loop, FX/remove buttons, volume + pan (with live numeric readouts).
    Lives in a non-horizontally-scrolling panel so it always stays visible.

    T016: every pixel position, size and font is stored at scale 1.0 and multiplied by the UI
    scale when placed; rescale() re-applies fonts / slider lengths and set_height() re-places."""

    def __init__(self, master, track, engine, on_change, on_remove, on_open_fx, **kw):
        super().__init__(master, **kw)
        self.track = track
        self.engine = engine
        self.on_change = on_change
        self.on_remove = on_remove
        self.on_open_fx = on_open_fx

        col = tk.Frame(self, bg="#1A1A1A", width=control_col_width(), height=_sc(TRACK_ROW_HEIGHT))
        col.pack(fill="both", expand=True)
        col.pack_propagate(False)
        self._col = col
        self._always = []        # (widget, base place kwargs): name and ARM / MUTE / SOLO row
        self._row2 = []          # (widget, base place kwargs): loop / FX / remove row, hidden on very low rows
        self._row3 = []          # (widget, base place kwargs): volume + pan rows, hidden on low rows
        self._fonts = []         # (widget, family, base size, weight)
        self._height = _sc(TRACK_ROW_HEIGHT)

        name_var = tk.StringVar(value=self.track.name)
        self._name_var = name_var

        def commit_name(*_):
            self.track.name = name_var.get()

        name_entry = tk.Entry(col, textvariable=name_var, bg="#2A2A2A", fg=self.track.color,
                               insertbackground="white", relief="flat")
        self.name_entry = name_entry
        self._always.append((name_entry, dict(x=6, y=4, width=CONTROL_COL_WIDTH - 12, height=20)))
        self._fonts.append((name_entry, "Segoe UI", 9, "bold"))
        name_entry.bind("<FocusOut>", commit_name)
        name_entry.bind("<Return>", commit_name)

        self.arm_var = tk.BooleanVar(value=self.track.armed)
        self.mute_var = tk.BooleanVar(value=self.track.mute)
        self.solo_var = tk.BooleanVar(value=self.track.solo)
        self.loop_var = tk.BooleanVar(value=self.track.loop_enabled)

        def toggle_arm():
            self.engine.arm_track(self.track, self.arm_var.get())
            self.on_change()

        def toggle_mute():
            self.track.mute = self.mute_var.get()
            self.on_change()

        def toggle_solo():
            self.track.solo = self.solo_var.get()
            self.on_change()

        def toggle_loop():
            if self.track.recording:
                # Recording + "loop this clip" are mutually exclusive by
                # design (see README) - revert the checkbox instead of
                # silently accepting a state the engine will ignore.
                self.loop_var.set(False)
                return
            self.track.loop_enabled = self.loop_var.get()
            self.on_change()

        chk_style = dict(bg="#1A1A1A", activebackground="#1A1A1A", selectcolor="#2A2A2A", anchor="w")
        self.arm_chk = tk.Checkbutton(col, text="ARM", variable=self.arm_var, command=toggle_arm,
                                       fg="#FF5555", **chk_style)
        self._always.append((self.arm_chk, dict(x=4, y=26, width=56)))
        mute_chk = tk.Checkbutton(col, text="MUTE", variable=self.mute_var, command=toggle_mute,
                                   fg="#FFCC00", **chk_style)
        self._always.append((mute_chk, dict(x=60, y=26, width=56)))
        solo_chk = tk.Checkbutton(col, text="SOLO", variable=self.solo_var, command=toggle_solo,
                                   fg="#00CFFF", **chk_style)
        self._always.append((solo_chk, dict(x=116, y=26, width=56)))
        self.loop_chk = tk.Checkbutton(col, text="LOOP CLIP", variable=self.loop_var, command=toggle_loop,
                                        fg="#00FF66", **chk_style)
        self._row2.append((self.loop_chk, dict(x=4, y=48, width=90)))
        for chk in (self.arm_chk, mute_chk, solo_chk, self.loop_chk):
            self._fonts.append((chk, "Segoe UI", 8, None))

        btn_style = dict(bg="#2A2A2A", fg="#DDDDDD", activebackground="#3A3A3A", activeforeground="#FFFFFF",
                         relief="flat", bd=0, highlightthickness=0, padx=0, pady=0)
        self.fx_btn = tk.Button(col, text="FX", command=lambda: self.on_open_fx(self.track), **btn_style)
        self._row2.append((self.fx_btn, dict(x=100, y=46, width=40, height=19)))
        self.rm_btn = tk.Button(col, text="X", command=self._confirm_remove, **btn_style)
        self._row2.append((self.rm_btn, dict(x=146, y=46, width=30, height=19)))
        self._fonts.append((self.fx_btn, "Segoe UI", 8, "bold"))
        self._fonts.append((self.rm_btn, "Segoe UI", 8, "bold"))

        vol_lbl = tk.Label(col, text="VOL", bg="#1A1A1A", fg="#888888")
        self._row3.append((vol_lbl, dict(x=4, y=68)))
        self.vol_scale = tk.Scale(col, from_=0.0, to=2.0, resolution=0.01, orient="horizontal",
                                   showvalue=False, length=_sc(94), bg="#1A1A1A", fg="#00FF66",
                                   troughcolor="#2A2A2A", highlightthickness=0,
                                   width=_sc(SLIDER_THICKNESS), sliderlength=_sc(SLIDER_LENGTH), bd=0,
                                   command=self._on_vol_change)
        self.vol_scale.set(self.track.gain)
        self._row3.append((self.vol_scale, dict(x=34, y=64)))
        self.vol_readout = tk.Label(col, text=self._fmt_vol(self.track.gain), bg="#1A1A1A",
                                     fg="#00FF66", width=5, anchor="w")
        self._row3.append((self.vol_readout, dict(x=130, y=68)))

        pan_lbl = tk.Label(col, text="PAN", bg="#1A1A1A", fg="#888888")
        self._row3.append((pan_lbl, dict(x=4, y=82)))
        self.pan_scale = tk.Scale(col, from_=-1.0, to=1.0, resolution=0.05, orient="horizontal",
                                   showvalue=False, length=_sc(94), bg="#1A1A1A", fg="#00CFFF",
                                   troughcolor="#2A2A2A", highlightthickness=0,
                                   width=_sc(SLIDER_THICKNESS), sliderlength=_sc(SLIDER_LENGTH), bd=0,
                                   command=self._on_pan_change)
        self.pan_scale.set(self.track.pan)
        self._row3.append((self.pan_scale, dict(x=34, y=78)))
        self.pan_readout = tk.Label(col, text=self._fmt_pan(self.track.pan), bg="#1A1A1A",
                                     fg="#00CFFF", width=5, anchor="w")
        self._row3.append((self.pan_readout, dict(x=130, y=82)))
        for lbl in (vol_lbl, pan_lbl):
            self._fonts.append((lbl, "Segoe UI", 7, None))
        for lbl in (self.vol_readout, self.pan_readout):
            self._fonts.append((lbl, "Consolas", 7, None))
        self._apply_fonts()
        self.set_height(self._height)

    def _apply_fonts(self):
        for widget, family, size, weight in self._fonts:
            widget.configure(font=_font(family, size, weight))

    def rescale(self):
        """UI scale changed: new fonts and slider lengths. The caller then calls set_height()
        with the new row height, which re-places every widget."""
        self._col.configure(width=control_col_width())
        for sc in (self.vol_scale, self.pan_scale):
            sc.configure(length=_sc(94), width=_sc(SLIDER_THICKNESS), sliderlength=_sc(SLIDER_LENGTH))
        self._apply_fonts()
        self.set_height(self._height)

    @staticmethod
    def _place_scaled(widget, kw, extra_y=0):
        out = {k: _sc(v) for k, v in kw.items()}
        if extra_y:
            out["y"] = out["y"] + _sc(extra_y)
        widget.place(**out)

    def focus_name(self):
        """Put the cursor in the track name box with the whole name selected (rename)."""
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")
        self.name_entry.icursor("end")

    def set_height(self, h):
        """Resize the control column to the track row height `h` (px, already multiplied by the UI
        scale). The name and the ARM / MUTE / SOLO row are always shown; the LOOP / FX / X row from
        70 px (at scale 1.0) up; the VOL and PAN sliders from 94 px up (they drift down a little on
        very tall rows). Positions are stored at scale 1.0 and scaled here."""
        h = int(h)
        self._height = h
        self._col.configure(height=h, width=control_col_width())
        base_h = h / max(theme.get_scale(), 1e-6)
        extra = max(0.0, base_h - TRACK_ROW_HEIGHT)
        for widget, kw in self._always:
            self._place_scaled(widget, kw)
        for widget, kw in self._row2:
            if base_h >= 70 - 1e-6:
                self._place_scaled(widget, kw, int(extra // 6))
            else:
                widget.place_forget()
        for widget, kw in self._row3:
            if base_h >= 94 - 1e-6:
                self._place_scaled(widget, kw, int(extra // 3))
            else:
                widget.place_forget()

    @staticmethod
    def _fmt_vol(v):
        return f"{v:.2f}x"

    @staticmethod
    def _fmt_pan(v):
        if abs(v) < 0.02:
            return "C"
        side = "L" if v < 0 else "R"
        return f"{abs(v):.2f}{side}"

    def _confirm_remove(self):
        from tkinter import messagebox
        if self.track.length > 0 or self.track.recording:
            ok = messagebox.askyesno(
                "Remove track",
                f"'{self.track.name}' has recorded audio on it. Remove this track anyway?\n"
                "This cannot be undone unless the project was already saved.")
            if not ok:
                return
        self.on_remove(self.track)

    def _on_vol_change(self, val):
        self.track.gain = float(val)
        self.vol_readout.config(text=self._fmt_vol(self.track.gain))

    def _on_pan_change(self, val):
        self.track.pan = float(val)
        self.pan_readout.config(text=self._fmt_pan(self.track.pan))

    def sync_from_model(self):
        """Refresh every checkbox/slider from the underlying Track without
        re-triggering their commands (Tk only fires a Checkbutton/Scale's
        `command` on direct user interaction, not on var.set()/set()). Used
        after any action that can change another track's state out from
        under it - e.g. arming one track auto-unarms the others, which
        previously left their ARM checkboxes visually still checked."""
        self.arm_var.set(self.track.armed)
        self.mute_var.set(self.track.mute)
        self.solo_var.set(self.track.solo)
        self.loop_var.set(self.track.loop_enabled)
        self.vol_scale.set(self.track.gain)
        self.pan_scale.set(self.track.pan)
        self.vol_readout.config(text=self._fmt_vol(self.track.gain))
        self.pan_readout.config(text=self._fmt_pan(self.track.pan))
        if self._name_var.get() != self.track.name:
            self._name_var.set(self.track.name)

    def set_recording_visual(self, is_recording):
        self._col.configure(bg="#241414" if is_recording else "#1A1A1A")


class WaveformCanvas(tk.Canvas):
    """The draggable waveform strip for one track (timeline area only, no
    controls).

    Old mode (virtual=False): the canvas is as wide as the whole arrangement and the
    parent scrolls it; the full clip is drawn every time.

    Viewport mode (virtual=True, used by tab_tracks): the canvas is only as wide as the
    window and draws just the columns that are on screen, starting at timeline pixel
    `scroll_px`. Drawing cost follows the window width, so any zoom level and any clip
    length stay fast. Row height follows `view.track_height` when the view has it."""

    def __init__(self, master, track, view, on_change, width_px=2400, virtual=False, **kw):
        self.virtual = bool(virtual)
        super().__init__(master, height=row_height(view) if self.virtual else TRACK_ROW_HEIGHT,
                         width=width_px, bg="#0F0F0F", highlightthickness=0, **kw)
        self.track = track
        self.view = view
        self.on_change = on_change
        self.width_px = width_px
        self.scroll_px = 0.0
        self._playhead_sec = 0.0
        self._last_size = None

        self._drag_start_x = None
        self._drag_start_offset = None
        self._dragged = False
        self._drag_fine = False

        # Clip editing aids (T015). All of this is view state, never saved in a project.
        self.selected = False
        self.on_select = None        # fn(track or None): the tab keeps "one selected clip"
        self.on_edit = None          # fn(track): double-click on the clip body (opens FX)
        self.on_rename = None        # fn(track): double-click on the clip name
        self.snap_points = None      # fn(track) -> list of seconds to snap to (None: playhead only)
        self._readout = None         # text shown while dragging / nudging, None = hidden
        self._snap_guide_sec = None  # timeline second of the snap target while dragging

        self.bind("<ButtonPress-1>", self._drag_press)
        self.bind("<B1-Motion>", self._drag_motion)
        self.bind("<ButtonRelease-1>", self._drag_release)
        self.bind("<Double-Button-1>", self._double_click)
        if self.virtual:
            self.bind("<Configure>", self._on_configure)
        self.redraw()

    # ---- viewport helpers -------------------------------------------------- #
    def set_scroll_px(self, px, redraw=True):
        self.scroll_px = max(0.0, float(px))
        if redraw:
            self.redraw()

    def _on_configure(self, event):
        if (event.width, event.height) != self._last_size:
            self._last_size = (event.width, event.height)
            self.redraw()

    def _viewport_w(self):
        w = self.winfo_width()
        return w if w > 1 else self.width_px

    def set_playhead_seconds(self, sec):
        """Playhead line on the waveform (viewport mode only)."""
        self._playhead_sec = sec
        if not self.virtual:
            return
        x = self.view.sec_to_px(sec) - self.scroll_px
        h = row_height(self.view)
        if self.find_withtag("playhead"):
            self.coords("playhead", x, 0, x, h)
        else:
            self.create_line(x, 0, x, h, fill="#FF3333", tags="playhead")

    # ---- drawing ------------------------------------------------------------ #
    def redraw(self):
        if self.virtual:
            self._redraw_viewport()
            return
        c = self
        c.delete("all")

        px_per_sec = self.view.px_per_sec
        total_sec = self.width_px / px_per_sec
        t = 0
        while t <= total_sec:
            x = self.view.sec_to_px(t)
            c.create_line(x, 0, x, TRACK_ROW_HEIGHT, fill="#1C1C1C")
            t += 1

        if self.track.length == 0:
            if self.track.recording:
                c.create_text(10, TRACK_ROW_HEIGHT / 2, anchor="w", fill="#FF3333",
                               font=_font("Segoe UI", 9, "bold"), text="\u25CF RECORDING...")
            else:
                c.create_text(10, TRACK_ROW_HEIGHT / 2, anchor="w", fill="#555555",
                               font=_font("Segoe UI", 9), text="Empty - ARM this track, then hit RECORD ARMED")
            return

        dur = self.track.duration_sec()
        x0 = self.view.sec_to_px(self.track.offset / self.track.sample_rate)
        w = max(2, int(self.view.sec_to_px(dur)))

        mid = TRACK_ROW_HEIGHT / 2
        mins, maxs = self.track.compute_peaks(w)
        if len(mins) == 0:
            return

        border = "#FF5555" if self.track.armed else self.track.color
        c.create_rectangle(x0, 6, x0 + w, TRACK_ROW_HEIGHT - 6, fill="#161616",
                            outline=border, width=2 if self.track.armed else 1, tags="clip")

        scale = (TRACK_ROW_HEIGHT / 2 - 8)
        n_cols = len(mins)
        if n_cols < w:
            # Stretch a short waveform (fewer computed columns than pixels
            # of screen width) across the full clip width instead of
            # bunching it into the first few pixels on the left.
            idx_map = [int(i * n_cols / w) for i in range(w)]
            mins = mins[idx_map]
            maxs = maxs[idx_map]

        points_top = []
        points_bot = []
        for i, (mn, mx) in enumerate(zip(mins, maxs)):
            x = x0 + i
            points_top.append((x, mid - mx * scale))
            points_bot.append((x, mid - mn * scale))
        poly = []
        poly.extend(points_top)
        poly.extend(reversed(points_bot))
        if len(poly) >= 4:
            c.create_polygon(poly, fill=self.track.color, outline="", stipple="", tags="clip")

        c.create_text(x0 + 6, 10, anchor="nw", fill="#DDDDDD", font=_font("Consolas", 8),
                       text=f"{self.track.name}  ({dur:.2f}s)"
                            + ("  \u21BB loop" if self.track.loop_enabled else ""))

    def _redraw_viewport(self):
        c = self
        c.delete("all")
        h = row_height(self.view)
        w = self._viewport_w()
        scroll = self.scroll_px
        track = self.track

        for tick in self.view.ticks(w, scroll):
            x = tick.x - scroll
            if -1 <= x <= w + 1:
                c.create_line(x, 0, x, h, fill="#242424" if tick.major else "#1C1C1C")

        if track.length == 0:
            if track.recording:
                c.create_text(10, h / 2, anchor="w", fill="#FF3333",
                               font=_font("Segoe UI", 9, "bold"), text="\u25CF RECORDING...")
            else:
                c.create_text(10, h / 2, anchor="w", fill="#555555",
                               font=_font("Segoe UI", 9), text="Empty - ARM this track, then hit RECORD ARMED")
            self.set_playhead_seconds(self._playhead_sec)
            return

        dur = track.duration_sec()
        pps = self.view.px_per_sec
        x0 = self.view.sec_to_px(track.offset / track.sample_rate) - scroll   # clip start on screen
        clip_w = self.view.sec_to_px(dur)
        mid = h / 2.0
        scale = h / 2.0 - 8

        left, right = max(x0, -4.0), min(x0 + clip_w, w + 4.0)
        if right > left:
            border = "#FF5555" if track.armed else track.color
            if self.selected:
                border = "#FFFFFF"
            c.create_rectangle(left, 6, right, h - 6, fill="#222222" if self.selected else "#161616",
                                outline=border, width=2 if (track.armed or self.selected) else 1,
                                tags=("clip", "selection") if self.selected else "clip")

        first = max(0, int(-x0 // 1))                       # first clip pixel column on screen
        last = min(int(clip_w) + 1, int(w - x0) + 1)          # one past the last
        if last - first >= 2:
            spp = track.length / max(clip_w, 1e-9)           # samples per pixel column
            mins, maxs = visible_peaks(track.buffer, first, last, spp)
            mins = np.clip(mins, -1.0, 1.0)
            maxs = np.clip(maxs, -1.0, 1.0)
            n = len(mins)
            xs = x0 + np.arange(first, first + n, dtype=np.float64)
            pts = np.empty((2 * n, 2), dtype=np.float64)
            pts[:n, 0] = xs
            pts[:n, 1] = mid - maxs * scale
            pts[n:, 0] = xs[::-1]
            pts[n:, 1] = (mid - mins * scale)[::-1]
            c.create_polygon(pts.ravel().tolist(), fill=track.color, outline="", tags="clip")

        if x0 + clip_w > 0 and x0 < w:
            c.create_text(max(x0, 0.0) + _sc(6), _sc(10), anchor="nw", fill="#DDDDDD", font=_font("Consolas", 8),
                           text=f"{track.name}  ({dur:.2f}s)" + ("  \u21BB loop" if track.loop_enabled else ""),
                           tags="label")
        if self._snap_guide_sec is not None:
            gx = self.view.sec_to_px(self._snap_guide_sec) - scroll
            c.create_line(gx, 0, gx, h, fill="#FFD400", dash=(3, 3), width=max(1, _sc(1)), tags="snapguide")
        if self._readout:
            rx = min(max(x0, 0.0) + _sc(6), max(float(_sc(6)), w - _sc(150)))
            t = c.create_text(rx + _sc(4), h - _sc(12), anchor="sw", fill="#FFD400", font=_font("Consolas", 9, "bold"),
                              text=self._readout, tags="readout")
            bx = c.bbox(t)
            if bx:
                bg = c.create_rectangle(bx[0] - 3, bx[1] - 1, bx[2] + 3, bx[3] + 1, fill="#000000",
                                        outline="#FFD400", tags="readout")
                c.tag_lower(bg, t)
        self.set_playhead_seconds(self._playhead_sec)

    # ------------------------------------------------------------------ #
    # Drag to reposition the clip along the timeline
    # ------------------------------------------------------------------ #
    def clip_span_px(self):
        """(left, right) of the clip in widget x pixels, or None when the track is empty."""
        if self.track.length == 0:
            return None
        x0 = self.view.sec_to_px(self.track.offset / self.track.sample_rate) - self.scroll_px
        return x0, x0 + self.view.sec_to_px(self.track.duration_sec())

    def hit_clip(self, x):
        """True when widget x pixel `x` is over the clip."""
        span = self.clip_span_px()
        return span is not None and span[0] <= x <= span[1]

    def set_selected(self, flag):
        flag = bool(flag)
        if flag != self.selected:
            self.selected = flag
            self.redraw()

    def show_readout(self, text):
        """Show (text) or hide (None) the offset readout on this strip."""
        if text != self._readout:
            self._readout = text
            self.redraw()

    def _snap_candidates(self):
        pts = list(self.snap_points(self.track)) if self.snap_points else []
        pts.append(self._playhead_sec)
        pts.append(0.0)
        return pts

    def _drag_press(self, event):
        self._dragged = False
        if self.virtual:
            self.focus_set()                     # leaves a name entry; arrow keys now reach the tab
            if not self.hit_clip(event.x):
                self._drag_start_x = None        # empty space: clear the selection, no drag
                if self.on_select:
                    self.on_select(None)
                return
            if self.on_select:
                self.on_select(self.track)
        self._drag_start_x = event.x
        self._drag_start_offset = self.track.offset
        self._drag_fine = bool(event.state & _SHIFT_BIT) if isinstance(event.state, int) else False

    def _drag_motion(self, event):
        if self._drag_start_x is None or self.track.recording:
            return
        state = event.state if isinstance(event.state, int) else 0
        fine = bool(state & _SHIFT_BIT)
        if fine != self._drag_fine:              # Shift pressed or released mid-drag: no jump
            self._drag_fine = fine
            self._drag_start_x = event.x
            self._drag_start_offset = self.track.offset
        dx_px = event.x - self._drag_start_x
        if abs(dx_px) > 1:
            self._dragged = True
        sr = self.track.sample_rate
        new_offset = drag_offset(self._drag_start_offset, dx_px, self.view.px_per_sec, sr, fine)
        self._snap_guide_sec = None
        if self.virtual and not (state & (_SHIFT_BIT | _ALT_BIT)):
            thr = snap_px() / self.view.px_per_sec
            sec, target = snap_offset_info(new_offset / float(sr), self._snap_candidates(), thr,
                                           self.track.duration_sec())
            if target is not None:
                new_offset = max(0, int(round(sec * sr)))
                self._snap_guide_sec = target
        self.track.offset = new_offset
        if self.virtual:
            self._readout = format_offset(self.track.offset, sr)
        self.redraw()

    def _drag_release(self, event):
        was_dragging = self._drag_start_x is not None
        self._drag_start_x = None
        self._drag_start_offset = None
        self._drag_fine = False
        self._snap_guide_sec = None
        had_readout = self._readout is not None
        self._readout = None
        if self._dragged:
            self.on_change()                     # same call as before: loop end is recomputed
        elif was_dragging and had_readout:
            self.redraw()
        self._dragged = False

    def _double_click(self, event):
        if not self.virtual or not self.hit_clip(event.x):
            return
        if self.on_select:
            self.on_select(self.track)
        label = self.bbox("label")
        if (label and label[0] <= event.x <= label[2] and label[1] <= event.y <= label[3]
                and self.on_rename):
            self.on_rename(self.track)           # double-click on the clip name: rename
        elif self.on_edit:
            self.on_edit(self.track)             # double-click on the clip: FX dialog


class TrackStrip:
    """Manages the paired (frozen) TrackHeader + (scrolling) WaveformCanvas
    for one track and keeps them packed into their respective parent
    containers. Not a widget itself."""

    def __init__(self, header_parent, waveform_parent, track, engine, view,
                 on_change, on_remove, on_open_fx, width_px=2400, virtual=False,
                 on_select=None, snap_points=None):
        self.track = track
        self.view = view
        self.header = TrackHeader(header_parent, track, engine, on_change, on_remove, on_open_fx)
        self.waveform = WaveformCanvas(waveform_parent, track, view, on_change, width_px=width_px,
                                        virtual=virtual)
        # Clip editing aids (T015); only the viewport-mode canvas of tab_tracks uses them.
        self.waveform.on_select = on_select
        self.waveform.snap_points = snap_points
        self.waveform.on_edit = on_open_fx
        self.waveform.on_rename = lambda _track: self.header.focus_name()
        self._row_h = None
        self._apply_height()
        view.add_listener(self.redraw)

    def pack(self):
        self.header.pack(fill="x", pady=ROW_PAD_Y)
        self.waveform.pack(fill="x", pady=ROW_PAD_Y)

    def destroy(self):
        if self.redraw in getattr(self.view, "listeners", ()):
            self.view.listeners.remove(self.redraw)
        self.header.destroy()
        self.waveform.destroy()

    def _apply_height(self):
        """Keep header and waveform at the view's row height (no-op for the old view)."""
        h = row_height(self.view)
        if h != self._row_h:
            self._row_h = h
            self.header.set_height(h)
            if self.waveform.virtual:
                self.waveform.configure(height=h)

    def rescale(self):
        """UI scale changed (T016): header fonts and positions, row height, waveform text."""
        self.header.rescale()
        self._row_h = None
        self._apply_height()
        self.waveform.redraw()

    def redraw(self):
        self._apply_height()
        self.waveform.redraw()
        self.header.set_recording_visual(self.track.recording)

    def sync_from_model(self):
        self.header.sync_from_model()
