"""
tabs.py  (Phase 9 / T010)
The tab contract for the main window and the default tabs.

    tab = tabs.load_tab("tracks", notebook, app)

`load_tab(name, parent, app)` imports module `tab_<name>` (tab_tracks, tab_mixer,
tab_audio, tab_debug) and uses its class `Tab(parent, app)` when that module exists.
Otherwise the default class below is used. Wave 4 tasks therefore only add a
`tab_<name>.py` file and never edit app.py or tabs.py.

Every tab is a ttk.Frame with:
    title        text on the tab header
    on_show()    called when the tab becomes the visible one
    on_tick()    called from the app's 150 ms loop while the tab is visible

The Tracks tab owns all timeline code and exposes add_track_strip(track),
remove_track_strip(track), rebuild_all(), refresh_states(), redraw_all(),
set_playhead(sec) and `view`; app.py only delegates to it.
"""
import importlib
import tkinter as tk
from tkinter import ttk

import ui_theme as theme
from scroll_frame import ScrollableFrame, bind_wheel
from waveform_widget import TimelineView, TimelineRuler, TrackStrip, CONTROL_COL_WIDTH

TAB_NAMES = ("tracks", "mixer", "audio", "debug", "lab")
TIMELINE_WIDTH_PX = 3000


def panelize(widget):
    """Give every ttk label, frame and button-like child of a LabelFrame panel the panel colour
    (#1E1E1E) instead of the window colour, so labels do not show a darker box."""
    p = theme.PALETTE
    style = ttk.Style(widget)
    style.configure("Panel.TFrame", background=p["surface1"])
    style.configure("Panel.TLabel", background=p["surface1"], foreground=p["text"], font=theme.font("UI"))
    for kind in ("Radiobutton", "Checkbutton"):
        style.configure(f"Panel.T{kind}", background=p["surface1"], foreground=p["text"],
                        font=theme.font("UI"))
        style.map(f"Panel.T{kind}", background=[("active", p["surface1"])])
    mapping = {"TFrame": "Panel.TFrame", "TLabel": "Panel.TLabel",
               "TRadiobutton": "Panel.TRadiobutton", "TCheckbutton": "Panel.TCheckbutton"}

    def walk(w):
        for child in w.winfo_children():
            cls = child.winfo_class()
            if cls in mapping:
                try:
                    child.configure(style=mapping[cls])
                except tk.TclError:
                    pass
            walk(child)
    walk(widget)


class BaseTab(ttk.Frame):
    title = "Tab"

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

    def on_show(self):
        pass

    def on_tick(self):
        pass


# ------------------------------------------------------------------ Tracks
class TracksTab(BaseTab):
    title = "Tracks"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.engine = app.engine
        self.view = TimelineView(px_per_sec=80.0)
        self.track_strips = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_hint_banner()
        self._build_timeline_area()

    # ---- first-run hint --------------------------------------------- #
    def _build_hint_banner(self):
        p = theme.PALETTE
        self.hint_frame = tk.Frame(self, bg=p["hint_bg"])
        self.hint_frame.grid(row=0, column=0, sticky="ew")
        self.hint_frame.columnconfigure(0, weight=1)
        text = ("Quick start:  1) Audio tab: pick an Input + Output device  \u2192  "
                "2) MOUNT AUDIO ENGINE  \u2192  3) + TRACK  \u2192  "
                "4) tick ARM on that track  \u2192  5) RECORD ARMED to capture audio.")
        tk.Label(self.hint_frame, text=text, bg=p["hint_bg"], fg=p["hint_fg"], font=theme.font("SMALL"),
                 anchor="w", justify="left", wraplength=1080).grid(
            row=0, column=0, sticky="ew", padx=12, pady=6)
        ttk.Button(self.hint_frame, text="Got it", style="Neutral.TButton",
                   command=self.hint_frame.grid_remove).grid(row=0, column=1, padx=10, pady=6)

    # ---- timeline (moved over unchanged from app.py) ------------------ #
    def _build_timeline_area(self):
        p = theme.PALETTE
        outer = ttk.Frame(self, padding=6)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(1, weight=1)
        self.outer = outer

        tk.Frame(outer, width=CONTROL_COL_WIDTH, height=28, bg=p["bg"]).grid(
            row=0, column=0, sticky="nsew")

        self.ruler = TimelineRuler(outer, self.view, self.engine.sample_rate, width_px=TIMELINE_WIDTH_PX)
        self.ruler.grid(row=0, column=1, sticky="ew")
        self.ruler.bind("<Button-1>", self._on_ruler_click)
        self.view.add_listener(self.ruler.redraw)

        self.header_canvas = tk.Canvas(outer, width=CONTROL_COL_WIDTH, bg=p["bg"], highlightthickness=0)
        self.header_canvas.grid(row=1, column=0, sticky="ns")
        self.header_frame = tk.Frame(self.header_canvas, bg=p["bg"])
        self.header_canvas.create_window((0, 0), window=self.header_frame, anchor="nw")
        self.header_frame.bind("<Configure>", lambda e: self.header_canvas.configure(
            scrollregion=self.header_canvas.bbox("all")))

        self.tracks_canvas = tk.Canvas(outer, bg=p["bg"], highlightthickness=0)
        self.tracks_canvas.grid(row=1, column=1, sticky="nsew")
        self.tracks_frame = tk.Frame(self.tracks_canvas, bg=p["bg"])
        self.tracks_canvas.create_window((0, 0), window=self.tracks_frame, anchor="nw")
        self.tracks_frame.bind("<Configure>", lambda e: self.tracks_canvas.configure(
            scrollregion=self.tracks_canvas.bbox("all")))

        self.empty_state_lbl = tk.Label(
            self.tracks_frame, bg=p["bg"], fg="#555555", font=theme.font("UI"),
            text="No tracks yet - click '+ TRACK' or 'IMPORT' above to get started.")
        self.empty_state_lbl.pack(pady=40)

        vscroll = ttk.Scrollbar(outer, orient="vertical", command=self._on_vscroll)
        vscroll.grid(row=1, column=2, sticky="ns")
        hscroll = ttk.Scrollbar(outer, orient="horizontal", command=self._on_hscroll)
        hscroll.grid(row=2, column=1, sticky="ew")
        self.tracks_canvas.configure(yscrollcommand=lambda a, b: vscroll.set(a, b),
                                     xscrollcommand=lambda a, b: hscroll.set(a, b))
        for widget in (self.header_canvas, self.tracks_canvas):
            bind_wheel(widget, self._on_wheel)

    def _on_vscroll(self, *args):
        self.header_canvas.yview(*args)
        self.tracks_canvas.yview(*args)

    def _on_hscroll(self, *args):
        self.ruler.xview(*args)
        self.tracks_canvas.xview(*args)

    def _on_wheel(self, direction, _event):
        step = -direction
        self.header_canvas.yview_scroll(step, "units")
        self.tracks_canvas.yview_scroll(step, "units")
        return "break"

    def _on_ruler_click(self, event):
        sec = self.ruler.x_to_seconds(event.x)
        self.engine.set_playhead_seconds(sec)
        self.ruler.set_playhead_seconds(sec)

    # ---- public interface used by app.py ------------------------------ #
    def add_track_strip(self, track):
        self.empty_state_lbl.pack_forget()
        strip = TrackStrip(self.header_frame, self.tracks_frame, track, self.engine, self.view,
                           on_change=self.app._on_track_changed, on_remove=self.app.remove_track,
                           on_open_fx=self.app.open_fx, width_px=TIMELINE_WIDTH_PX)
        strip.pack()
        self.track_strips[track.id] = strip
        return strip

    def remove_track_strip(self, track):
        strip = self.track_strips.pop(track.id, None)
        if strip:
            strip.destroy()
        self._relayout()

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

    def refresh_states(self):
        for strip in self.track_strips.values():
            strip.sync_from_model()
            strip.redraw()

    def redraw_all(self):
        for strip in self.track_strips.values():
            strip.redraw()

    def set_playhead(self, sec):
        self.ruler.set_playhead_seconds(sec)

    def redraw_recording(self):
        """Redraw only strips that are recording (the app calls this every 60 ms)."""
        for strip in self.track_strips.values():
            if strip.track.recording:
                strip.redraw()


# ------------------------------------------------------------------- Mixer
class MixerTab(BaseTab):
    title = "Mixer"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        p = theme.PALETTE
        card = tk.Frame(self, bg=p["surface1"])
        card.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(card, text="Mixer", bg=p["surface1"], fg=p["accent"], font=theme.font("TITLE")).pack(
            padx=40, pady=(24, 4))
        tk.Label(card, text="Channel strips, master strip and inline FX rack are coming here.\n"
                            "For now use the FX button on each track and MASTER FX in the top bar.",
                 bg=p["surface1"], fg=p["muted"], font=theme.font("UI"), justify="center").pack(
            padx=40, pady=(0, 24))


# ------------------------------------------------------------------- Audio
class AudioTab(BaseTab):
    title = "Audio"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.scroll = ScrollableFrame(self, vertical=True, horizontal=False)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        body = self.scroll.body
        body.columnconfigure(0, weight=1)
        self.panel = app.create_audio_panel(body)
        self.panel.grid(row=0, column=0, padx=16, pady=8, sticky="ew")
        self.options = self._build_options(body)
        self.options.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        self.load_graph = self._build_load(body)
        self.load_graph.grid(row=2, column=0, padx=16, pady=8, sticky="ew")

    def _build_options(self, parent):
        p = theme.PALETTE
        box = ttk.LabelFrame(parent, text=" INPUT / OUTPUT OPTIONS ", padding=12)
        specs = (("\u21AA  INPUT LOOPBACK (always hear live input in the output)",
                  "monitor_var", self.app._on_monitor_toggle, "#00CFFF"),
                 ("\u21A9  OUTPUT LOOPBACK (fold current mix into new recordings)",
                  "rec_output_var", self.app._on_rec_output_toggle, "#FF9900"),
                 ("\u2728 CLEAN INPUT (DC blocker + gentle noise expander)",
                  "cleanup_var", self.app._on_cleanup_toggle, "#66FF99"))
        for text, attr, cmd, color in specs:
            tk.Checkbutton(box, text=text, variable=getattr(self.app, attr), command=cmd,
                           bg=p["surface1"], activebackground=p["surface1"], selectcolor=p["surface2"],
                           fg=color, activeforeground=color, font=theme.font("UI_BOLD"),
                           anchor="w").pack(fill="x", pady=2)
        return box

    def _build_load(self, parent):
        p = theme.PALETTE
        box = ttk.LabelFrame(parent, text=" LOAD (callback time per block) ", padding=12)
        self.app.load_graph = tk.Canvas(box, width=theme.scaled(360), height=theme.scaled(40),
                                        bg="#0A0A0A", highlightthickness=0)
        self.app.load_graph.pack(anchor="w")
        return box


# ------------------------------------------------------------------- Debug
class DebugTab(BaseTab):
    title = "Debug"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.center = app.create_debug_center(self)
        self.center.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self.center.columnconfigure(0, weight=1)
        self.center.rowconfigure(2, weight=1)
        self.center.nb.grid_configure(sticky="nsew")
        for tab_id in self.center.nb.tabs():
            frame = self.center.nb.nametowidget(tab_id)
            frame.rowconfigure(0, weight=1)
            for child in frame.winfo_children():
                if isinstance(child, (tk.Text, ttk.Treeview)):
                    child.grid_configure(sticky="nsew")
                    try:
                        child.configure(height=1)
                    except tk.TclError:
                        pass
            for w in frame.winfo_children():
                if isinstance(w, ttk.Scrollbar):
                    w.grid_configure(sticky="ns")


# ------------------------------------------------------------------ loader
class LabTab(BaseTab):
    """Placeholder used only if tab_lab.py cannot be imported (T021 provides the real tab)."""
    title = "Lab"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="Lab tab not available.").grid(row=0, column=0, padx=16, pady=16)


_DEFAULTS = {"tracks": TracksTab, "mixer": MixerTab, "audio": AudioTab, "debug": DebugTab,
             "lab": LabTab}


def load_tab(name, parent, app):
    """Create the tab `name`: class Tab of module tab_<name> when it exists, else the default."""
    cls = _DEFAULTS[name]
    try:
        mod = importlib.import_module(f"tab_{name}")
    except ImportError as e:
        if getattr(e, "name", None) != f"tab_{name}":
            raise            # the module exists but one of its own imports is broken
    else:
        cls = getattr(mod, "Tab", cls)
    return cls(parent, app)
