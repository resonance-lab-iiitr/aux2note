"""
app.py
Live Looper Pro - main application window (Phase 9: tabbed, full-screen shell).

Layout:
  menu bar     File (New, Open, Save, Import audio, Export mixdown, Quit) and
               View (tabs Ctrl+1..5, full screen F11, timeline zoom)
  top bar      always visible: PLAY, REWIND, RECORD ARMED, time, LOOP, master
               volume, MASTER FX; second row: engine state, CPU / dropouts /
               peak, round trip, IN / OUT meters, track count
  notebook     Tracks | Mixer | Audio | Debug  (see tabs.py for the tab contract;
               a module tab_<name>.py with class Tab(parent, app) replaces a default tab)

Keyboard shortcuts (ignored while typing in a text field; work on every tab):
  Space  - Play / Stop          R   - Record armed tracks / stop recording
  Home   - Rewind to start      F12 - Debug tab + test-signal bar
  Ctrl+1..5 - select a tab      F11 - full screen on / off
  Ctrl+N / O / S - new / open / save project
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from audio_engine import AudioEngine
from audio_settings_panel import AudioSettingsPanel
import settings_store
from telemetry import format_status, rtt_text, short_mode, load_color, WARN_LOAD
import latency_core
from track import Track
from fx_dialog import FxDialog, MasterFxDialog
import debug_log
import power_plan
from debug_center import DebugCenter
import project_io
import tabs
import ui_theme as theme
from version import APP_NAME, APP_VERSION


UI_SCALE_STEP = 0.1     # Ctrl +, Ctrl -: 10 percent per press
TOP_BAR_WRAP_SCALE = 1.3   # from here the top bar uses two lines for its buttons
MASTER_VOL_LENGTH = 60     # T028: master slider length at scale 1.0 (was 100; MASTER FX was clipped at 1366 px)


class LiveLooperApp:
    def __init__(self, root):
        self.root = root
        self._after_ids = {}
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1180x900")
        theme.apply_theme(self.root)

        self.dlog = debug_log.DebugLog()
        debug_log.install_exception_hooks(self.dlog, root, notify=self._notify_error)
        self._device_rows = []
        self._fx_cost = None
        self.settings = settings_store.load_settings()
        self._applied_settings = dict(self.settings)
        theme.set_scale(self.settings.get("ui_scale", 1.0))      # T016: restore before tabs exist
        theme.add_scale_listener(self._on_ui_scale)
        self.engine = AudioEngine(sample_rate=self.settings["sample_rate"],
                                  block_size=self.settings["block_size"], log=self.log)
        self.current_project_path = None
        self.export_in_progress = False
        self._last_xruns = 0
        self._last_overruns = 0
        self.fullscreen = False

        self.engine.debug_rt = self.dlog

        self.build_ui()
        self._draw_load_graph(None)
        self.bind_shortcuts()
        self._maximize()

        self._after("logs", 30, self.process_logs)
        self._after("playhead", 60, self.tick_playhead)
        self._after("telemetry", 150, self.update_telemetry)
        self._after("debug", 500, self._refresh_debug_tab)

        self.refresh_devices()

    def _after(self, key, ms, fn):
        """Schedule a repeating UI timer and remember its id so on_close() can cancel it."""
        try:
            self._after_ids[key] = self.root.after(ms, fn)
        except tk.TclError:
            pass

    def cancel_timers(self):
        for ident in list(self._after_ids.values()):
            try:
                self.root.after_cancel(ident)
            except tk.TclError:
                pass
        self._after_ids.clear()

    # ------------------------------------------------------------------ #
    # Tab access (the Tracks tab owns the timeline; these keep old names working)
    # ------------------------------------------------------------------ #
    @property
    def view(self):
        return self.tracks_tab.view

    @property
    def track_strips(self):
        return self.tracks_tab.track_strips

    @property
    def ruler(self):
        return self.tracks_tab.ruler

    def select_tab(self, which):
        """Show a tab by name ('tracks', 'mixer', 'audio', 'debug') or index 0-3."""
        name = tabs.TAB_NAMES[which] if isinstance(which, int) else which
        self.notebook.select(self.tab_widgets[name])

    def current_tab_name(self):
        current = self.notebook.select()
        for name, widget in self.tab_widgets.items():
            if str(widget) == str(current):
                return name
        return None

    def _on_tab_changed(self, _event=None):
        name = self.current_tab_name()
        if name:
            self.tab_widgets[name].on_show()

    def _tick_visible_tab(self):
        name = self.current_tab_name()
        if name:
            self.tab_widgets[name].on_tick()

    # ------------------------------------------------------------------ #
    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # Option variables live on the app so every tab can show them.
        self.loop_var = tk.BooleanVar(value=False)
        self.monitor_var = tk.BooleanVar(value=False)
        self.rec_output_var = tk.BooleanVar(value=False)
        self.cleanup_var = tk.BooleanVar(value=True)    # rc10: DC blocker + noise expander

        self._build_menu()
        self._build_top_bar()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.tab_widgets = {}
        for name in tabs.TAB_NAMES:
            tab = tabs.load_tab(name, self.notebook, self)
            self.tab_widgets[name] = tab
            self.notebook.add(tab, text=f"  {tab.title}  ")
        self.tracks_tab = self.tab_widgets["tracks"]
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ------------------------------------------------------------------ #
    # Window: maximized start, full screen
    # ------------------------------------------------------------------ #
    def _maximize(self):
        try:
            self.root.state("zoomed")                 # Windows
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)  # Linux / X11
            except tk.TclError:
                pass
        self._after("maximize", 300, self._ensure_maximized)

    def is_maximized(self):
        try:
            if self.root.state() == "zoomed":
                return True
        except tk.TclError:
            pass
        try:
            if int(self.root.attributes("-zoomed")):
                return True
        except tk.TclError:
            pass
        return False

    def _ensure_maximized(self):
        """Fallback when the window manager ignored the request (or there is none)."""
        try:
            self.root.update_idletasks()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            if self.root.winfo_width() < sw * 0.9 or self.root.winfo_height() < sh * 0.8:
                self.root.geometry(f"{sw}x{sh}+0+0")
        except tk.TclError:
            pass

    def toggle_fullscreen(self, _event=None):
        self.fullscreen = not self.fullscreen
        try:
            self.root.attributes("-fullscreen", self.fullscreen)
        except tk.TclError:
            self.fullscreen = False
        return "break"

    # ------------------------------------------------------------------ #
    def _build_menu(self):
        p = theme.PALETTE
        opts = dict(bg=p["surface1"], fg=p["text"], activebackground=p["surface3"],
                    activeforeground=p["accent"], tearoff=0)
        menubar = tk.Menu(self.root, **opts)
        filem = tk.Menu(menubar, **opts)
        filem.add_command(label="New project", accelerator="Ctrl+N", command=self.new_project)
        filem.add_command(label="Open project...", accelerator="Ctrl+O", command=self.load_project)
        filem.add_command(label="Save project...", accelerator="Ctrl+S", command=self.save_project)
        filem.add_separator()
        filem.add_command(label="Import audio...", command=self.import_audio)
        filem.add_command(label="Export mixdown...", command=self.export_mix)
        filem.add_separator()
        filem.add_command(label="Quit", command=self.on_close)
        menubar.add_cascade(label="File", menu=filem)
        viewm = tk.Menu(menubar, **opts)
        for i, name in enumerate(tabs.TAB_NAMES):
            viewm.add_command(label=name.capitalize() + " tab", accelerator=f"Ctrl+{i + 1}",
                              command=lambda n=name: self.select_tab(n))
        viewm.add_separator()
        viewm.add_command(label="Full screen", accelerator="F11", command=self.toggle_fullscreen)
        viewm.add_separator()
        viewm.add_command(label="Timeline zoom in", command=lambda: self.view.zoom(1.25))
        viewm.add_command(label="Timeline zoom out", command=lambda: self.view.zoom(0.8))
        viewm.add_separator()
        viewm.add_command(label="UI scale larger", accelerator="Ctrl+Plus",
                          command=lambda: self.change_ui_scale(+UI_SCALE_STEP))
        viewm.add_command(label="UI scale smaller", accelerator="Ctrl+Minus",
                          command=lambda: self.change_ui_scale(-UI_SCALE_STEP))
        viewm.add_command(label="UI scale reset (100%)", accelerator="Ctrl+0",
                          command=lambda: self.change_ui_scale(None))
        menubar.add_cascade(label="View", menu=viewm)
        self.root.config(menu=menubar)
        self.menubar = menubar

    # ------------------------------------------------------------------ #
    def create_audio_panel(self, parent):
        """Called by the Audio tab: build the AUDIO SETTINGS panel inside `parent`."""
        self.audio_panel = AudioSettingsPanel(parent, on_mount=self.toggle_engine,
                                              on_change=self._on_settings_changed, log=self.log,
                                              on_calibrate=self.calibrate_latency)
        self.mount_btn = self.audio_panel.mount_btn
        tabs.panelize(self.audio_panel)
        return self.audio_panel

    def create_debug_center(self, parent):
        """Called by the Debug tab: build the Debug Center inside `parent`."""
        self.debug_center = DebugCenter(
            parent, self.dlog, self.engine,
            get_settings=lambda: self.audio_panel.get_settings(),
            get_device_rows=lambda: self._device_rows,
            on_rescan=self._rescan_devices, cost_provider=self._get_fx_cost)
        self.console = self.debug_center.console
        return self.debug_center


    def _on_settings_changed(self):
        """Called when the user changes any audio setting."""
        new = self.audio_panel.get_settings()
        if self.engine.is_active:
            old = self._applied_settings
            keys = [k for k in new if k not in ("record_offset_ms", "calibration")]
            if any(new[k] != old.get(k) for k in keys):
                if messagebox.askyesno(
                        "Change audio settings",
                        "The audio engine is running. Unmount and mount again with the "
                        "new settings now?"):
                    self._unmount()
                    self._mount()
                else:
                    self.audio_panel.apply_settings(old)
                return
        self.settings = new
        self._save_settings(new)

    def _build_top_bar(self):
        p = theme.PALETTE
        bg = p["surface1"]
        bar = tk.Frame(self.root, bg=bg)
        bar.grid(row=0, column=0, sticky="ew")
        self.top_bar = bar

        row1 = tk.Frame(bar, bg=bg)
        row1.pack(fill="x", padx=8, pady=(6, 2))
        self.top_row1 = row1
        # + TRACK / IMPORT / EXPORT live in their own frame so a large UI scale can move them to a
        # second line (T016); at 1366 px wide the first line is full from about 130 percent.
        self.top_right = tk.Frame(bar, bg=bg)
        self.top_row_wrap = tk.Frame(bar, bg=bg)           # shown only when the scale is large
        self.play_btn = ttk.Button(row1, text="\u25B6 PLAY", style="Action.TButton",
                                   command=self.toggle_play, state="disabled")
        self.play_btn.pack(side="left", padx=3)
        self.rewind_btn = ttk.Button(row1, text="\u23EE REWIND", style="Neutral.TButton",
                                     command=self.rewind, state="disabled")
        self.rewind_btn.pack(side="left", padx=3)
        self.rec_btn = ttk.Button(row1, text="\u25CF RECORD ARMED", style="Stop.TButton",
                                  command=self.toggle_record, state="disabled")
        self.rec_btn.pack(side="left", padx=3)
        self.time_lbl = tk.Label(row1, text="00:00.0", bg=bg, fg=p["text"], font=theme.font("TITLE"),
                                 width=7)
        self.time_lbl.pack(side="left", padx=(8, 4))

        tk.Checkbutton(row1, text="\u21BB LOOP", variable=self.loop_var,
                       command=self._on_loop_toggle, bg=bg, activebackground=bg,
                       selectcolor=p["surface2"], fg=p["accent"], activeforeground=p["accent"],
                       font=theme.font("UI_BOLD")).pack(side="left", padx=(6, 10))

        tk.Label(row1, text="Master", bg=bg, fg=p["muted"], font=theme.font("SMALL")).pack(side="left")
        self.master_vol = tk.Scale(row1, from_=0.0, to=2.0, resolution=0.01, orient="horizontal",
                                   bg=bg, fg=p["accent"], troughcolor=p["surface2"],
                                   highlightthickness=0, showvalue=True, font=theme.font("SMALL"),
                                   length=theme.scaled(MASTER_VOL_LENGTH), command=self._on_master_vol)
        self.master_vol.set(1.0)
        self.master_vol.pack(side="left", padx=(4, 4))

        self.top_right.pack(side="right")
        self.export_btn = ttk.Button(self.top_right, text="EXPORT MIX \u2193", style="Action.TButton",
                                     command=self.export_mix)
        self.export_btn.pack(side="right", padx=3)
        ttk.Button(self.top_right, text="IMPORT", style="Neutral.TButton",
                   command=self.import_audio).pack(side="right", padx=3)
        ttk.Button(self.top_right, text="+ TRACK", style="Neutral.TButton",
                   command=self.add_empty_track).pack(side="right", padx=3)
        ttk.Button(self.top_right, text="MASTER FX", style="Fx.TButton",
                   command=self.open_master_fx).pack(side="right", padx=3)

        row2 = tk.Frame(bar, bg=bg)
        row2.pack(fill="x", padx=8, pady=(2, 6))
        self.status_lbl = tk.Label(row2, text="ENGINE IDLE", bg=p["surface2"], fg=p["muted"],
                                   font=theme.font("UI_BOLD"), padx=10, pady=2)
        self.status_lbl.pack(side="left", padx=3)
        self.stats_lbl = tk.Label(row2, text="engine not mounted", bg=bg, fg="#666666",
                                  font=theme.font("MONO"))
        self.stats_lbl.pack(side="left", padx=8)
        self.rtt_lbl = tk.Label(row2, text="", bg=bg, fg=p["muted"], font=theme.font("MONO"))
        self.rtt_lbl.pack(side="left", padx=8)

        self.track_count_lbl = tk.Label(row2, text="0 tracks", bg=bg, fg="#666666",
                                        font=theme.font("SMALL"))
        self.track_count_lbl.pack(side="right", padx=8)
        mw, mh = theme.scaled(110), theme.scaled(10)
        self.out_meter = tk.Canvas(row2, width=mw, height=mh, bg="#0A0A0A", highlightthickness=0)
        self.out_meter.pack(side="right", padx=4)
        tk.Label(row2, text="OUT", bg=bg, fg=p["muted"], font=theme.font("SMALL")).pack(side="right")
        self.in_meter = tk.Canvas(row2, width=mw, height=mh, bg="#0A0A0A", highlightthickness=0)
        self.in_meter.pack(side="right", padx=(4, 14))
        tk.Label(row2, text="IN", bg=bg, fg=p["muted"], font=theme.font("SMALL")).pack(side="right")
        self._layout_top_bar()
        self._bar_width = 0
        self.root.bind("<Configure>", self._on_root_configure, add="+")

    def _on_root_configure(self, event):
        """T028: re-check the top bar wrap only when the window WIDTH changed."""
        if event.widget is not self.root:
            return
        w = int(event.width)
        if w == self._bar_width:
            return
        self._bar_width = w
        try:
            self.root.after_idle(self._layout_top_bar)
        except tk.TclError:
            pass

    def _top_bar_needs_wrap(self):
        """T028: True when the first line (left controls + the right button group) would be wider
        than the window, whatever the fonts of this PC are. Measured from the requested widths."""
        try:
            self.root.update_idletasks()
            left = 0
            for w in self.top_row1.pack_slaves():
                if w is self.top_right:
                    continue
                px = w.pack_info().get("padx", 0)
                px = sum(int(v) for v in px) if isinstance(px, (tuple, list)) else 2 * int(px)
                left += w.winfo_reqwidth() + px
            need = left + self.top_right.winfo_reqwidth() + 16 + 6      # row padx 2x8 + slack
            avail = self.root.winfo_width()
            if avail < 300:                      # not mapped yet: use the screen
                avail = self.root.winfo_screenwidth()
            return need > avail
        except (tk.TclError, AttributeError):
            return False

    def _layout_top_bar(self):
        """From TOP_BAR_WRAP_SCALE up (or when the first line would not fit the window), the
        + TRACK / IMPORT / EXPORT buttons move to a second line under the transport so nothing
        is cut off on a 1366 px wide screen."""
        if theme.get_scale() >= TOP_BAR_WRAP_SCALE or self._top_bar_needs_wrap():
            self.top_row_wrap.pack(fill="x", padx=8, pady=(0, 2), after=self.top_row1)
            self.top_right.pack_configure(in_=self.top_row_wrap, side="right")
            self.top_right.lift()          # a re-parented frame sits below its new parent
        else:
            self.top_right.pack_configure(in_=self.top_row1, side="right")
            self.top_right.lift()
            self.top_row_wrap.pack_forget()

    # ------------------------------------------------------------------ #
    # UI scale (T016): Ctrl +, Ctrl -, Ctrl 0, View menu, settings.json
    # ------------------------------------------------------------------ #
    def change_ui_scale(self, delta):
        """delta > 0 larger, delta < 0 smaller (10 percent steps), None = back to 100 percent."""
        cur = theme.get_scale()
        new = 1.0 if delta is None else round(cur + delta, 2)
        new = max(theme.SCALE_MIN, min(theme.SCALE_MAX, new))
        if abs(new - cur) < 1e-9:
            return cur
        theme.set_scale(new)          # fonts, ttk metrics, then every listener (tabs + _on_ui_scale)
        self._save_settings(self.settings)
        self.log(f"UI scale {int(round(new * 100))}%.", "SYS")
        return new

    def _save_settings(self, settings):
        """Save audio settings together with the current UI scale (the audio panel does not know it)."""
        data = dict(settings)
        data["ui_scale"] = theme.get_scale()
        self.settings = dict(self.settings)
        self.settings["ui_scale"] = data["ui_scale"]
        return settings_store.save_settings(data)

    def _on_ui_scale(self, scale):
        """Scale listener: resize the pixel-sized widgets of the top bar."""
        try:
            self.master_vol.config(length=theme.scaled(MASTER_VOL_LENGTH))
            mw, mh = theme.scaled(110), theme.scaled(10)
            for c in (self.in_meter, self.out_meter):
                c.config(width=mw, height=mh)
            self.status_lbl.config(padx=theme.scaled(10), pady=theme.scaled(2))
            self._layout_top_bar()
            self._draw_meter(self.in_meter, 0.0)
            self._draw_meter(self.out_meter, 0.0)
        except (tk.TclError, AttributeError):
            pass

    def _on_master_vol(self, val):
        self.engine.master_gain = float(val)

    def _on_loop_toggle(self):
        self.engine.set_loop_enabled(self.loop_var.get())

    def _on_cleanup_toggle(self):
        self.engine.input_cleanup_enabled = self.cleanup_var.get()
        self.log("Clean input (DC blocker + noise expander) "
                 + ("ON." if self.cleanup_var.get() else "OFF."), "SYS")

    def _on_monitor_toggle(self):
        self.engine.input_monitor_enabled = self.monitor_var.get()
        state = "ON" if self.monitor_var.get() else "OFF"
        self.log(f"Input loopback monitoring {state}.", "SYS")

    def _on_rec_output_toggle(self):
        self.engine.record_with_output_enabled = self.rec_output_var.get()
        state = "ON" if self.rec_output_var.get() else "OFF"
        self.log(f"Output loopback into recordings {state}.", "SYS")

    def open_master_fx(self):
        MasterFxDialog.open_for_master(self.root, self.engine)

    # ------------------------------------------------------------------ #
    # Keyboard shortcuts
    # ------------------------------------------------------------------ #
    def bind_shortcuts(self):
        self.root.bind_all("<space>", self._shortcut_play)
        self.root.bind_all("r", self._shortcut_record)
        self.root.bind_all("R", self._shortcut_record)
        self.root.bind_all("<Home>", self._shortcut_rewind)
        self.root.bind_all("<F12>", self._shortcut_debug)
        self.root.bind_all("<F11>", self.toggle_fullscreen)
        for i in range(len(tabs.TAB_NAMES)):
            self.root.bind_all(f"<Control-Key-{i + 1}>",
                               lambda e, n=i: (self.select_tab(n), "break")[1])
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.root.bind_all(seq, lambda e: (self.change_ui_scale(+UI_SCALE_STEP), "break")[1])
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.root.bind_all(seq, lambda e: (self.change_ui_scale(-UI_SCALE_STEP), "break")[1])
        for seq in ("<Control-Key-0>", "<Control-KP_0>"):
            self.root.bind_all(seq, lambda e: (self.change_ui_scale(None), "break")[1])
        self.root.bind_all("<Control-n>", lambda e: (self.new_project(), "break")[1])
        self.root.bind_all("<Control-o>", lambda e: (self.load_project(), "break")[1])
        self.root.bind_all("<Control-s>", lambda e: (self.save_project(), "break")[1])

    def _shortcut_debug(self, event=None):
        """F12: open the Debug tab and show / hide the test-signal bar."""
        if self.current_tab_name() != "debug":
            self.select_tab("debug")
            self.root.update_idletasks()
            if not self.debug_center.test_bar.winfo_manager():
                self.debug_center.toggle_test_bar()
            return "break"
        self.debug_center.toggle_test_bar()
        return "break"

    def _typing_in_entry(self, event):
        widget = event.widget
        return isinstance(widget, (tk.Entry, tk.Text))

    def _shortcut_play(self, event):
        if self._typing_in_entry(event):
            return
        if str(self.play_btn["state"]) != "disabled":
            self.toggle_play()
        return "break"

    def _shortcut_record(self, event):
        if self._typing_in_entry(event):
            return
        if str(self.rec_btn["state"]) != "disabled":
            self.toggle_record()

    def _shortcut_rewind(self, event):
        if self._typing_in_entry(event):
            return
        if str(self.rewind_btn["state"]) != "disabled":
            self.rewind()

    # ------------------------------------------------------------------ #
    # Logging (every line goes to the ring buffer + logs/looper.log at once)
    # ------------------------------------------------------------------ #
    def log(self, text, prefix="INFO"):
        self.dlog.add(text, prefix)

    def process_logs(self):
        self.debug_center.pump()
        # rc9: ttk returns a Tcl object (not a str) for cget("state"), so the old
        # `== "disabled"` test never matched and the button stayed on RENDERING.
        if not self.export_in_progress and "RENDERING" in str(self.export_btn.cget("text")):
            self.export_btn.config(state="normal", text="EXPORT MIX \u2193")
        self._after("logs", 30, self.process_logs)

    def _refresh_debug_tab(self):
        try:
            self.debug_center.refresh()
        finally:
            self._after("debug", 500, self._refresh_debug_tab)

    def _notify_error(self, title, msg):
        try:
            self.root.after(0, lambda: messagebox.showwarning(title, msg))
        except Exception:
            pass

    def _get_fx_cost(self):
        """Per-effect cost in % of a block (quick benchmark, done once)."""
        if self._fx_cost is None:
            try:
                import effects
                c = effects.benchmark_costs(self.engine.sample_rate, self.engine.block_size, reps=60)
                names = {"EQ (5 band)": "eq", "Compressor": "compressor", "Distortion": "distortion",
                         "Delay": "delay", "Reverb": "reverb"}
                self._fx_cost = {names[k]: v for k, v in c.items() if k in names}
            except Exception as e:
                self.log(f"Cost benchmark failed: {e}", "WARN")
                self._fx_cost = {}
        return self._fx_cost

    def _rescan_devices(self):
        if self.engine.is_active:
            self.log("Unmount the audio engine before rescanning devices.", "WARN")
            return
        self.refresh_devices()

    # ------------------------------------------------------------------ #
    # Hardware
    # ------------------------------------------------------------------ #
    @staticmethod
    def _preferred_index(entries, rows, default_key):
        """Pick the dropdown entry to preselect: a WASAPI device (needed for
        exclusive mode), preferring the Windows default device. Falls back
        to the first entry."""
        default_ids = {r["id"] for r in rows if r.get(default_key)}
        wasapi = [i for i, (dev_id, label) in enumerate(entries) if "[Windows WASAPI]" in label]
        for i in wasapi:
            if entries[i][0] in default_ids:
                return i
        # the default device is often listed under MME/DirectSound: match by name
        names = {r["name"] for r in rows if r["id"] in default_ids}
        for i in wasapi:
            dev_id = entries[i][0]
            nm = next((r["name"] for r in rows if r["id"] == dev_id), None)
            if nm in names:
                return i
        return wasapi[0] if wasapi else 0

    def refresh_devices(self):
        """Startup diagnostic: log every audio driver/device the OS exposes,
        then populate the input/output dropdowns from that same scan."""
        self.log("=" * 78, "BOOT")
        self.log("           AUDIO DRIVER & DEVICE INVENTORY (FULL SYSTEM SCAN)", "BOOT")
        self.log("=" * 78, "BOOT")
        try:
            rows, err = self.engine.probe_all_devices()
            self._device_rows = rows or []
            if err:
                self.log(f"Device probe error: {err}", "CRIT")
            for r in rows:
                tags = []
                if r["is_default_in"]:
                    tags.append("DEFAULT-IN")
                if r["is_default_out"]:
                    tags.append("DEFAULT-OUT")
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                self.log(
                    f"ID {r['id']:02d} | Driver: {r['driver']:<14} | "
                    f"In:{r['max_in']:>2} Out:{r['max_out']:>2} | "
                    f"{r['default_sr']:.0f} Hz | {r['name']}{tag_str}", "PROBE")
            self.log("=" * 78, "BOOT")

            inputs, outputs = self.engine.list_devices()
            self.audio_panel.set_devices(inputs, outputs, rows, saved=self.settings)
            if not inputs or not outputs:
                self.log("No usable input/output device(s) found - the engine cannot mount "
                          "until at least one of each is available on this system.", "WARN")
            self.log(f"{len(rows)} device(s) total | {len(inputs)} usable input(s), "
                      f"{len(outputs)} usable output(s). Select devices and MOUNT AUDIO ENGINE.", "SYS")
        except Exception as e:
            self.log(f"Device scan failed: {e}", "CRIT")

    def toggle_engine(self):
        if not self.engine.is_active:
            self._mount()
        else:
            self._unmount()

    def _mount(self):
        try:
            cfg = self.audio_panel.get_config()
            if cfg.in_device is None or cfg.out_device is None:
                self.log("Select both an input and output device first.", "ERROR")
                return
            self.engine.open_stream(cfg.in_device, cfg.out_device, cfg)
            self._last_xruns = self._last_overruns = 0
            self.audio_panel.set_mounted(True)
            self._restore_calibration()
            self._applied_settings = self.audio_panel.get_settings()
            self.settings = dict(self._applied_settings)
            self._save_settings(self.settings)
            self.play_btn.config(state="normal", text="\u25B6 PLAY", style="Action.TButton")
            self.rewind_btn.config(state="normal")
            self.rec_btn.config(state="normal")
            self.status_lbl.config(text="ENGINE RUNNING", fg=theme.PALETTE["accent"])
            self.log(f"Audio engine mounted ({self.engine.mode_name}). Press PLAY to start the transport.", "SUCCESS")
            if self.engine.active_config is not None and self.engine.active_config.exclusive:
                self.log("[AUDIO] Exclusive mode: other programs cannot use this sound card until you UNMOUNT.", "WARN")
            warn = power_plan.warning_for(power_plan.get_active_scheme())
            if warn:
                self.log(warn, "WARN")
        except Exception as e:
            self.log(f"Failed to mount audio engine: {e}", "CRIT")
            messagebox.showerror(
                "Could not mount audio engine",
                f"{e}\n\nCheck that the selected input/output devices support the "
                "engine's sample rate and aren't already in use by another app.")

    # ------------------------------------------------------------------ #
    # Phase 5: latency calibration
    # ------------------------------------------------------------------ #
    def _restore_calibration(self):
        """After MOUNT: reuse the saved calibration if it was made for the
        exact mode that is running now (e.g. 'WASAPI EXCL 48000/64')."""
        cal = self.audio_panel.calibration
        key = short_mode(self.engine)
        if cal and cal["key"] == key:
            self.engine.set_calibration(cal["rtt_ms"], key)
            self.log(f"[CALIB] Using saved calibration: RTT {cal['rtt_ms']:.1f} ms ({key}).", "SYS")
        elif cal:
            self.log(f"[CALIB] Saved calibration is for {cal['key']}, not {key}: press "
                     "CALIBRATE LATENCY again.", "WARN")

    def calibrate_latency(self):
        if not self.engine.is_active:
            self.log("Mount the audio engine before calibrating.", "WARN")
            return
        if any(t.recording for t in self.engine.tracks):
            self.log("Stop recording before calibrating.", "WARN")
            return
        if not messagebox.askokcancel(
                "Calibrate latency",
                "Connect a cable from Line Out (green) to Line In (blue).\n"
                "Turn off 'Listen to this device' for the input.\n"
                "Set the Windows playback volume to about 50%.\n\n"
                "Test sounds will play for about 6 seconds. Press OK to start."):
            return
        self.audio_panel.calib_btn.config(state="disabled", text="CALIBRATING ...")
        self.log("[CALIB] Started. Do not touch the audio settings for 6 seconds.", "SYS")

        def work():
            try:
                res, err = self.engine.run_calibration(), None
            except Exception as e:
                res, err = None, str(e)
            self.root.after(0, lambda: self._calibration_done(res, err))
        threading.Thread(target=work, daemon=True).start()

    def _calibration_done(self, res, err):
        self.audio_panel.calib_btn.config(
            state="normal" if self.engine.is_active else "disabled", text="CALIBRATE LATENCY")
        if err:
            self.log(f"[CALIB] Failed: {err}", "ERROR")
            messagebox.showerror("Calibration failed", err)
            return
        ok = res["status"] == latency_core.STATUS_OK
        if ok:
            cal = {"rtt_ms": res["rtt_ms"], "key": self.engine.calibration["key"]}
            self.audio_panel.set_calibration(cal)
            self.audio_panel.set_offset_ms(res["rtt_ms"])
            self._applied_settings = self.audio_panel.get_settings()
            self.settings = dict(self._applied_settings)
            self._save_settings(self.settings)
            self.engine.record_latency_samples = settings_store.ms_to_samples(
                self.audio_panel.record_offset_ms(), self.engine.sample_rate)
        lines = [f"Status:  {res['status']}"]
        if res["rtt_ms"] is not None:
            lines += [f"Round trip (RTT):  {res['rtt_ms']:.2f} ms  ({res['rtt_samples']} samples)",
                      f"Jitter:  {res['jitter_ms']:.2f} ms"]
        lines += [f"Signal level:  {res['level_dbfs']:.1f} dBFS",
                  f"Bursts detected:  {res['bursts_ok']} of {res['bursts']}", "",
                  latency_core.ADVICE[res["status"]]]
        if ok:
            lines += ["Record offset set to the measured RTT."]
        (messagebox.showinfo if ok else messagebox.showwarning)(
            "Latency calibration", "\n".join(lines))

    def _unmount(self):
        self.engine.close_stream()
        self.audio_panel.set_mounted(False)
        self.play_btn.config(state="disabled", text="\u25B6 PLAY", style="Action.TButton")
        self.rewind_btn.config(state="disabled")
        self.rec_btn.config(state="disabled", text="\u25CF RECORD ARMED")
        self.status_lbl.config(text="ENGINE IDLE", fg="#888888")
        self.stats_lbl.config(text="engine not mounted", fg="#666666")
        self.rtt_lbl.config(text="")
        self._draw_load_graph(None)
        self.log("Audio engine unmounted.", "SYS")

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    def toggle_play(self):
        if self.engine.is_playing:
            self.engine.stop()
            self.play_btn.config(text="\u25B6 PLAY", style="Action.TButton")
        else:
            self.engine.play()
            self.play_btn.config(text="\u23F8 STOP", style="Stop.TButton")

    def rewind(self):
        self.engine.rewind()
        sec = self.engine.playhead / float(self.engine.sample_rate)
        self.tracks_tab.set_playhead(sec)
        self._set_time(sec)

    def toggle_record(self):
        armed_tracks = [t for t in self.engine.tracks if t.armed]
        if not armed_tracks:
            self.log("Arm at least one track (checkbox 'ARM') before recording.", "WARN")
            return
        any_recording = any(t.recording for t in self.engine.tracks)
        if not any_recording:
            overwriting = [t for t in armed_tracks if t.length > 0]
            if overwriting:
                names = ", ".join(t.name for t in overwriting)
                ok = messagebox.askyesno(
                    "Overwrite existing take?",
                    f"'{names}' already has recorded audio. Recording now will replace "
                    "it entirely and cannot be undone. Continue?")
                if not ok:
                    return
            # start_recording_armed() also starts the transport (see
            # AudioEngine) so existing tracks play back while overdubbing;
            # reflect that in the PLAY button immediately.
            self.engine.record_latency_samples = settings_store.ms_to_samples(
                self.audio_panel.record_offset_ms(), self.engine.sample_rate)
            self.engine.start_recording_armed()
            self.play_btn.config(text="\u23F8 STOP", style="Stop.TButton")
            self.rec_btn.config(text="\u25A0 STOP RECORDING")
            self.refresh_track_ui_states()
            self.log(f"Recording started on {len(armed_tracks)} armed track(s).", "LOOPER")
        else:
            self.engine.stop_recording_armed()
            self.rec_btn.config(text="\u25CF RECORD ARMED")
            # Explicit refresh, not just a wait for the next tick_playhead()
            # pass: tick_playhead only redraws strips that are still
            # `recording`, and that flag is now False, so without this the
            # strip would freeze on its last "RECORDING..." frame forever -
            # no waveform, no drag handles, looking exactly like the app
            # never actually stopped. See refresh_track_ui_states().
            self.refresh_track_ui_states()
            self.log("Recording stopped and committed to track buffer.", "LOOPER")

    # ------------------------------------------------------------------ #
    # Track management
    # ------------------------------------------------------------------ #
    def add_empty_track(self):
        track = Track(f"Track {len(self.engine.tracks) + 1}", self.engine.sample_rate)
        self.engine.add_track(track)
        self._add_track_strip(track)
        self.log(f"Added empty track '{track.name}'. Arm it and hit Record to capture audio.", "SYS")

    def import_audio(self):
        path = filedialog.askopenfilename(
            title="Import Audio",
            filetypes=[("Audio files", "*.wav *.mp3 *.flac *.ogg *.aiff *.aif"), ("All files", "*.*")])
        if not path:
            return
        track = Track(os.path.splitext(os.path.basename(path))[0], self.engine.sample_rate)
        try:
            track.import_audio(path, at_sample=self.engine.playhead)
        except Exception as e:
            messagebox.showerror("Import failed", str(e))
            self.log(f"Import failed: {e}", "ERROR")
            return
        self.engine.add_track(track)
        self._add_track_strip(track)
        self.log(f"Imported '{os.path.basename(path)}' as new track ({track.duration_sec():.2f}s).", "SUCCESS")

    def remove_track(self, track):
        self.engine.remove_track(track)
        self.tracks_tab.remove_track_strip(track)
        self._update_track_count()
        self.log(f"Removed track '{track.name}'.", "SYS")

    def open_fx(self, track):
        FxDialog.open_for(self.root, track, key=track.id)

    def _add_track_strip(self, track):
        self.tracks_tab.add_track_strip(track)
        self._update_track_count()

    def _update_track_count(self):
        n = len(self.engine.tracks)
        self.track_count_lbl.config(text=f"{n} track{'s' if n != 1 else ''}")
        self.audio_panel.set_rate_locked(n > 0)   # rate is fixed once tracks exist

    def _on_track_changed(self):
        self.engine._recompute_loop_end()
        self.refresh_track_ui_states()

    def refresh_track_ui_states(self):
        """Re-sync every visible strip's checkboxes/sliders with the model,
        AND redraw its waveform canvas.

        The waveform redraw matters just as much as the checkbox sync here:
        tick_playhead() only redraws a strip's canvas while its track is
        still `recording` (so the "RECORDING..." placeholder updates live
        without redrawing every idle track 16x/sec). The instant recording
        stops - whether via the RECORD button or because arming a different
        track auto-stopped this one - `track.recording` flips to False
        *before* this function runs, so tick_playhead's own `if
        strip.track.recording` check now excludes it and would never draw
        it again. Without the explicit redraw() here, the strip stays
        stuck on its last "RECORDING..." frame forever: no waveform, no
        drag handles, nothing - exactly as if the recording never stopped,
        even though the engine and button state are correct underneath."""
        self.tracks_tab.refresh_states()

    def rebuild_all_strips(self):
        self.tracks_tab.rebuild_all()
        self._update_track_count()

    def new_project(self):
        has_audio = any(t.length > 0 for t in self.engine.tracks)
        if self.engine.tracks:
            msg = ("Start a new, empty project? All current tracks will be removed."
                   + ("\n\nUnsaved recorded audio will be lost." if has_audio else ""))
            if not messagebox.askyesno("New project", msg):
                return
        self.engine.clear_all_tracks()
        self.rebuild_all_strips()
        self.current_project_path = None
        self.loop_var.set(False)
        self.play_btn.config(text="\u25B6 PLAY", style="Action.TButton")
        self.rec_btn.config(text="\u25CF RECORD ARMED")
        self.log("New project started.", "SYS")

    # ------------------------------------------------------------------ #
    # Periodic UI refresh
    # ------------------------------------------------------------------ #
    def tick_playhead(self):
        self.engine.housekeeping()
        sec = self.engine.playhead / float(self.engine.sample_rate)
        self.tracks_tab.set_playhead(sec)
        self._set_time(sec)
        self.tracks_tab.redraw_recording()
        self._after("playhead", 60, self.tick_playhead)

    def _set_time(self, sec):
        """Time readout in the top bar, mm:ss.t"""
        sec = max(0.0, float(sec))
        text = f"{int(sec // 60):02d}:{sec % 60:04.1f}"
        if self.time_lbl.cget("text") != text:
            self.time_lbl.config(text=text)

    def update_telemetry(self):
        self._tick_visible_tab()
        if self.engine.is_active:
            tel = self.engine.telemetry
            peak = max(self.engine.peak_l, self.engine.peak_r)
            load = tel.cpu_load()
            color = load_color(load, peak)
            transport = "PLAYING" if self.engine.is_playing else "STOPPED"
            self.status_lbl.config(text=f"RUNNING [{transport}]", fg=color)
            self.stats_lbl.config(text=format_status(self.engine, with_rtt=False), fg=color)
            measured = self.engine.measured_rtt_ms() is not None
            self.rtt_lbl.config(text=rtt_text(self.engine),
                                fg="#00CCFF" if measured else "#888888")
            self._draw_load_graph(tel)
            self._log_new_dropouts(tel)
            self._draw_meter(self.in_meter, self.engine.input_peak)
            self._draw_meter(self.out_meter, peak)
            # Keep the PLAY button honest if the transport was started by
            # something other than the button itself (e.g. auto-play on
            # record), or stopped by unmounting.
            want_text = "\u23F8 STOP" if self.engine.is_playing else "\u25B6 PLAY"
            if self.play_btn["text"] != want_text:
                style = "Stop.TButton" if self.engine.is_playing else "Action.TButton"
                self.play_btn.config(text=want_text, style=style)
        else:
            self._draw_meter(self.in_meter, 0.0)
            self._draw_meter(self.out_meter, 0.0)
        self._after("telemetry", 150, self.update_telemetry)

    def _log_new_dropouts(self, tel):
        """One log line per tick at most (never from the audio thread)."""
        if tel.xruns > self._last_xruns:
            n = tel.xruns - self._last_xruns
            self._last_xruns = tel.xruns
            self.log(f"[AUDIO] {n} dropout(s) reported by the sound card "
                     f"(total {tel.xruns}). Try a larger block size or fewer effects.", "WARN")
        if tel.overruns > self._last_overruns:
            n = tel.overruns - self._last_overruns
            self._last_overruns = tel.overruns
            self.log(f"[AUDIO] {n} block(s) took longer than the block time "
                     f"(total {tel.overruns}, worst {tel.peak_load() * 100:.0f}%).", "WARN")

    def _draw_load_graph(self, tel):
        """Callback time per block as bars. Full height = 150 % of the block
        time; the red line marks 100 % (the block time). Bars above 70 % are red."""
        c = self.load_graph
        c.delete("all")
        w = int(c["width"])
        h = int(c["height"])
        c.create_rectangle(0, 0, w - 1, h - 1, outline="#333333")
        if tel is None:
            return
        loads = tel.history_loads()
        n = len(loads)
        bar_w = max(1.0, w / float(n))
        for i, v in enumerate(loads):
            if v <= 0:
                continue
            bh = min(h - 2, (v / 1.5) * (h - 2))
            col = "#FF3333" if v > WARN_LOAD else "#00AA55"
            x0 = i * bar_w
            c.create_rectangle(x0, h - 1 - bh, x0 + bar_w, h - 1, fill=col, outline="")
        y100 = (h - 1) - (1.0 / 1.5) * (h - 2)
        c.create_line(0, y100, w, y100, fill="#FF3333")

    def _draw_meter(self, canvas, level):
        canvas.delete("all")
        w = int(canvas["width"])
        h = int(canvas["height"])
        filled = max(0, min(w, int(level * w)))
        color = "#00FF66" if level < 0.7 else ("#FFCC00" if level < 0.9 else "#FF3333")
        if filled > 0:
            canvas.create_rectangle(0, 0, filled, h, fill=color, outline="")
        canvas.create_rectangle(0, 0, w, h, outline="#333333")

    # ------------------------------------------------------------------ #
    # Project save / load
    # ------------------------------------------------------------------ #
    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".llproj",
                                             filetypes=[("Live Looper Pro Project", "*.llproj")])
        if not path:
            return
        try:
            project_io.save_project(path, self.engine)
            self.current_project_path = path
            self.log(f"Project saved: {path}", "SUCCESS")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            self.log(f"Project save failed: {e}", "ERROR")

    def load_project(self):
        path = filedialog.askopenfilename(filetypes=[("Live Looper Pro Project", "*.llproj")])
        if not path:
            return
        try:
            tracks, transport = project_io.load_project(path, self.engine.sample_rate)
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            self.log(f"Project load failed: {e}", "ERROR")
            return

        audio = transport.get("audio", {})
        if audio.get("sample_rate") and audio["sample_rate"] != self.engine.sample_rate:
            if self.engine.is_active:
                self.log(f"[AUDIO] Project is {audio['sample_rate']} Hz but the engine runs at "
                         f"{self.engine.sample_rate} Hz. UNMOUNT and load again to switch.", "WARN")
            else:
                self.engine._apply_sample_rate(audio["sample_rate"])
        if not self.engine.is_active:
            self.audio_panel.set_rate_block(audio.get("sample_rate"),
                                            audio.get("block_size") if audio.get("present") else None)
        with self.engine.lock:
            self.engine.tracks = tracks
            self.engine.loop_enabled = transport.get("loop_enabled", False)
            self.engine.loop_start = transport.get("loop_start", 0)
            self.engine.loop_end = transport.get("loop_end", 0)
            self.engine.master_gain = transport.get("master_gain", 1.0)
            if transport.get("master_fx"):
                self.engine.master_fx_l.from_dict(transport["master_fx"])
                self.engine.master_fx_r.from_dict(transport["master_fx"])
            self.engine.input_monitor_enabled = transport.get("input_monitor_enabled", False)
            self.engine.record_with_output_enabled = transport.get("record_with_output_enabled", False)
            self.engine.monitor_gain = transport.get("monitor_gain", 1.0)
            self.engine._recompute_loop_end()

        self.loop_var.set(self.engine.loop_enabled)
        self.monitor_var.set(self.engine.input_monitor_enabled)
        self.rec_output_var.set(self.engine.record_with_output_enabled)
        self.master_vol.set(self.engine.master_gain)
        self.rebuild_all_strips()
        self.current_project_path = path
        self.log(f"Project loaded: {path} ({len(tracks)} track(s)).", "SUCCESS")

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def export_mix(self):
        if self.export_in_progress:
            return
        if not self.engine.tracks:
            messagebox.showinfo("Nothing to export", "Add or record at least one track first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 Audio", "*.mp3"), ("WAV Audio", "*.wav")])
        if not path:
            return
        self.export_in_progress = True
        self.export_btn.config(state="disabled", text="RENDERING\u2026")
        self.log("Rendering mixdown...", "SYS")
        # Snapshot everything the render needs under the engine lock before
        # handing off to the worker thread, so a track being added/removed
        # or a recording committing mid-export can't race the renderer.
        tracks_snapshot = self.engine.snapshot_tracks()
        with self.engine.lock:
            master_gain = self.engine.master_gain
            master_fx_snapshot = self.engine.master_fx_l.clone()
        threading.Thread(target=self._export_worker,
                          args=(path, tracks_snapshot, master_gain, master_fx_snapshot),
                          daemon=True).start()

    def _export_worker(self, path, tracks_snapshot, master_gain, master_fx_snapshot):
        try:
            stereo = project_io.render_mix(
                tracks_snapshot, self.engine.sample_rate,
                loop_count=1, master_gain=master_gain,
                master_fx=master_fx_snapshot)
            if path.lower().endswith(".mp3"):
                try:
                    project_io.export_mp3(path, stereo, self.engine.sample_rate)
                except ImportError:
                    wav_path = os.path.splitext(path)[0] + ".wav"
                    project_io.export_wav(wav_path, stereo, self.engine.sample_rate)
                    self.log("`lameenc` not installed - exported WAV instead: " + wav_path, "WARN")
                    self.log("Run: pip install lameenc  (then export again for MP3).", "WARN")
                    return
            else:
                project_io.export_wav(path, stereo, self.engine.sample_rate)
            self.log(f"Mixdown exported: {path}", "SUCCESS")
        except Exception as e:
            self.log(f"Export failed: {e}", "ERROR")
        finally:
            self.export_in_progress = False

    # ------------------------------------------------------------------ #
    def on_close(self):
        self.cancel_timers()
        theme.remove_scale_listener(self._on_ui_scale)
        self._save_settings(self.audio_panel.get_settings())
        self.engine.close_stream()
        self.dlog.close()
        self.root.destroy()
