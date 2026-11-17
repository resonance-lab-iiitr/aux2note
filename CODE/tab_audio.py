"""
tab_audio.py  (Phase 9 / T012)
The Audio tab: devices + calibration (AudioSettingsPanel), monitoring and input options,
and a big live status view (mode, RTT, CPU, dropouts, IN / OUT meters, load graph).

Replaces tabs.AudioTab through tabs.load_tab("audio", ...). The app's own variables
(monitor_var, rec_output_var, cleanup_var) and toggle handlers are reused; app.audio_panel,
app.mount_btn and app.load_graph are set here, as app.py expects.
"""
import tkinter as tk
from tkinter import ttk

import ui_theme as theme
from scroll_frame import ScrollableFrame
from tabs import BaseTab, panelize
from telemetry import short_mode, rtt_text, load_color

NOT_MOUNTED_TEXT = "not mounted"
_STAT_KEYS = ("mode", "rtt", "cpu", "dropouts")


class Tab(BaseTab):
    title = "Audio"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.scroll = ScrollableFrame(self, vertical=True, horizontal=False)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        body = self.scroll.body
        body.columnconfigure(0, weight=3, uniform="audio")
        body.columnconfigure(1, weight=2, uniform="audio")

        # left column: devices + calibration (one panel with two sections)
        self.panel = app.create_audio_panel(body)
        self.panel.grid(row=0, column=0, rowspan=2, padx=(16, 8), pady=8, sticky="new")

        # right column: monitoring / input options, then the live status
        self.options = self._build_options(body)
        self.options.grid(row=0, column=1, padx=(8, 16), pady=8, sticky="new")
        self.status_box = self._build_status(body)
        self.status_box.grid(row=1, column=1, padx=(8, 16), pady=8, sticky="new")

        self.sections = {"devices": self.panel.devices_frame,
                         "calibration": self.panel.calib_frame,
                         "monitoring": self.options,
                         "status": self.status_box}
        panelize(self.options)
        panelize(self.status_box)
        self.refresh_status()
        theme.add_scale_listener(self._on_scale)      # T016: canvases have fixed pixel sizes

    # ---------------------------------------------------------------- UI scale (T016)
    def _on_scale(self, scale):
        """Resize the fixed-size canvases (IN / OUT meters, load graph) to the new scale."""
        try:
            mw, mh = theme.scaled(260), theme.scaled(16)
            for c in (self.big_in_meter, self.big_out_meter):
                c.config(width=mw, height=mh)
            self.load_graph.config(width=theme.scaled(300), height=theme.scaled(56))
            self.app._draw_load_graph(None)
            self.refresh_status()
        except tk.TclError:
            pass

    def destroy(self):
        theme.remove_scale_listener(self._on_scale)
        super().destroy()

    # ---------------------------------------------------------------- monitoring
    def _build_options(self, parent):
        p = theme.PALETTE
        box = ttk.LabelFrame(parent, text=" MONITORING AND INPUT ", padding=12)
        specs = (("\u21AA  INPUT LOOPBACK", "hear live input in the output",
                  "monitor_var", self.app._on_monitor_toggle, "#00CFFF"),
                 ("\u21A9  OUTPUT LOOPBACK", "fold the current mix into new recordings",
                  "rec_output_var", self.app._on_rec_output_toggle, "#FF9900"),
                 ("\u2728 CLEAN INPUT", "DC blocker + gentle noise expander",
                  "cleanup_var", self.app._on_cleanup_toggle, "#66FF99"))
        self.option_checks = {}
        for i, (text, hint, attr, cmd, color) in enumerate(specs):
            cb = tk.Checkbutton(box, text=text, variable=getattr(self.app, attr), command=cmd,
                                bg=p["surface1"], activebackground=p["surface1"],
                                selectcolor=p["surface2"], fg=color, activeforeground=color,
                                font=theme.font("UI_BOLD"), anchor="w")
            cb.grid(row=2 * i, column=0, sticky="w", pady=(4, 0))
            tk.Label(box, text=hint, bg=p["surface1"], fg=p["muted"], font=theme.font("SMALL"),
                     anchor="w").grid(row=2 * i + 1, column=0, sticky="w", padx=(26, 0))
            self.option_checks[attr] = cb
        return box

    # ---------------------------------------------------------------- live status
    def _build_status(self, parent):
        p = theme.PALETTE
        box = ttk.LabelFrame(parent, text=" LIVE STATUS ", padding=12)
        box.columnconfigure(1, weight=1)
        mono, small = theme.font("MONO"), theme.font("SMALL")
        self.stat_vars = {}
        self.stat_labels = {}
        rows = (("mode", "Mode"), ("rtt", "Round trip"), ("cpu", "CPU load"), ("dropouts", "Dropouts"))
        for i, (key, caption) in enumerate(rows):
            tk.Label(box, text=caption, bg=p["surface1"], fg=p["muted"], font=small,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="-")
            lbl = tk.Label(box, textvariable=var, bg=p["surface1"], fg=p["text"], font=mono, anchor="w")
            lbl.grid(row=i, column=1, sticky="w", padx=(12, 0), pady=2)
            self.stat_vars[key] = var
            self.stat_labels[key] = lbl

        mw, mh = theme.scaled(260), theme.scaled(16)
        self.big_in_meter = self._meter_row(box, 4, "IN", mw, mh)
        self.big_out_meter = self._meter_row(box, 5, "OUT", mw, mh)

        tk.Label(box, text="Callback time per block (red line = block time)", bg=p["surface1"],
                 fg=p["muted"], font=small, anchor="w").grid(row=6, column=0, columnspan=2,
                                                             sticky="w", pady=(10, 2))
        # app._draw_load_graph reads this canvas's "width" / "height" options
        self.load_graph = tk.Canvas(box, width=theme.scaled(300), height=theme.scaled(56),
                                    bg="#0A0A0A", highlightthickness=0)
        self.load_graph.grid(row=7, column=0, columnspan=2, sticky="w")
        self.app.load_graph = self.load_graph
        return box

    def _meter_row(self, box, row, caption, w, h):
        p = theme.PALETTE
        tk.Label(box, text=caption, bg=p["surface1"], fg=p["muted"], font=theme.font("SMALL"),
                 anchor="w").grid(row=row, column=0, sticky="w", pady=(8 if row == 4 else 2, 2))
        canvas = tk.Canvas(box, width=w, height=h, bg="#0A0A0A", highlightthickness=0)
        canvas.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=(8 if row == 4 else 2, 2))
        return canvas

    # ---------------------------------------------------------------- updating
    def on_show(self):
        self.refresh_status()

    def on_tick(self):
        self.refresh_status()

    def refresh_status(self):
        """Redraw the status area. Called from the app's 150 ms loop while this tab is visible."""
        engine = self.app.engine
        muted = theme.PALETTE["muted"]
        if not engine.is_active:
            self.stat_vars["mode"].set(NOT_MOUNTED_TEXT)
            for key in ("rtt", "cpu", "dropouts"):
                self.stat_vars[key].set("-")
            for lbl in self.stat_labels.values():
                lbl.config(fg=muted)
            self.app._draw_meter(self.big_in_meter, 0.0)
            self.app._draw_meter(self.big_out_meter, 0.0)
            return
        tel = engine.telemetry
        peak = max(engine.peak_l, engine.peak_r)
        load = tel.cpu_load()
        color = load_color(load, peak)
        measured = engine.measured_rtt_ms() is not None
        self.stat_vars["mode"].set(short_mode(engine))
        self.stat_vars["rtt"].set(rtt_text(engine).replace("RTT ", "", 1))
        self.stat_vars["cpu"].set(f"{load * 100:.0f}%  (worst {tel.peak_load() * 100:.0f}%)")
        self.stat_vars["dropouts"].set(f"{tel.xruns} card, {tel.overruns} late blocks")
        self.stat_labels["mode"].config(fg=color)
        self.stat_labels["rtt"].config(fg="#00CCFF" if measured else muted)
        self.stat_labels["cpu"].config(fg=color)
        self.stat_labels["dropouts"].config(
            fg=theme.PALETTE["error"] if (tel.xruns or tel.overruns) else theme.PALETTE["text"])
        self.app._draw_meter(self.big_in_meter, engine.input_peak)
        self.app._draw_meter(self.big_out_meter, peak)
