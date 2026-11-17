"""
debug_center.py  (Live Looper Pro v2.0, Phase 6; reworked in Phase 9 / T013)

DEBUG CENTER: sub-tabs Log / Engine / Devices / Tracks / Load / Report, the COPY DEBUG
REPORT button and the F12 test-signal bar. All data comes from debug_log.py.

Log:     level chips, search with match count, pause auto-scroll, clear view.
Engine:  value cards (state, mode, CPU, RTT, dropouts, blocks, peak) above the full table.
Devices / Tracks: click a column heading to sort (click again to reverse).
Load:    callback time per block with the 100 % (block time) line.
Report:  preview of the debug report text (REFRESH / COPY).
Sub-tab order matters (refresh() uses the index): Log 0, Engine 1, Devices 2, Tracks 3, Load 4, Report 5.
"""
import tkinter as tk
from tkinter import ttk

import debug_log as dl
import ui_theme as theme

LEVEL_COLORS = {"DEBUG": "#6C8F6C", "INFO": "#00FF66", "WARN": "#FFCC00",
                "ERROR": "#FF5555", "CRIT": "#FF2222"}
MAX_LINES = 500
TAB_LOG, TAB_ENGINE, TAB_DEVICES, TAB_TRACKS, TAB_LOAD, TAB_REPORT = range(6)
CARDS = (("state", "STATE"), ("mode", "MODE"), ("cpu", "CPU"), ("rtt", "ROUND TRIP"),
         ("drops", "DROPOUTS"), ("split", "SPLIT HAND-OFF"), ("blocks", "BLOCKS"), ("peak", "PEAK L / R / IN"))


def _sort_key(v):
    try:
        return (0, float(str(v).replace(",", "")), "")
    except ValueError:
        return (1, 0.0, str(v).lower())


class DebugCenter(ttk.LabelFrame):
    def __init__(self, parent, dlog, engine, get_settings, get_device_rows,
                 on_rescan, cost_provider=None):
        super().__init__(parent, text=" DEBUG CENTER ", padding=6)
        self.dlog, self.engine = dlog, engine
        self.get_settings, self.get_device_rows = get_settings, get_device_rows
        self.on_rescan, self.cost_provider = on_rescan, cost_provider
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._clear_ts = 0.0                 # log lines older than this are hidden (Clear)
        self._lines = 0                      # lines currently in the console
        self._sort = {}                      # treeview -> (column, reverse)
        self._tree_cols = {}
        self._tree_widths = {}               # treeview -> base column widths at scale 1.0 (T016)
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.level_var = tk.StringVar(value="DEBUG")
        self.search_var = tk.StringVar()

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.copy_btn = ttk.Button(bar, text="COPY DEBUG REPORT", style="Action.TButton",
                                   command=self.copy_report)
        self.copy_btn.pack(side="left")
        ttk.Label(bar, text="  Search:").pack(side="left")
        ent = ttk.Entry(bar, textvariable=self.search_var, width=22)
        ent.pack(side="left")
        self.search_var.trace_add("write", lambda *a: self.rerender())
        self.match_lbl = ttk.Label(bar, text="0 lines", style="Muted.TLabel", width=12)
        self.match_lbl.pack(side="left", padx=6)
        ttk.Label(bar, text="   F12 = test signal", style="Muted.TLabel").pack(side="right")

        self.test_bar = ttk.Frame(self)           # hidden until F12
        self.test_kind = tk.StringVar(value="sine")
        ttk.Label(self.test_bar, text="TEST SIGNAL (plays instead of the looper; keep volume low):"
                  ).pack(side="left")
        ttk.Radiobutton(self.test_bar, text="Sine 440 Hz", variable=self.test_kind,
                        value="sine").pack(side="left", padx=4)
        ttk.Radiobutton(self.test_bar, text="Noise", variable=self.test_kind,
                        value="noise").pack(side="left", padx=4)
        self.test_btn = ttk.Button(self.test_bar, text="START", style="Neutral.TButton",
                                   command=self.toggle_test)
        self.test_btn.pack(side="left", padx=6)

        self.nb = ttk.Notebook(self)
        self.nb.grid(row=2, column=0, sticky="nsew")
        self.console = self._tab_log()
        self._tab_engine()
        self.dev_tree = self._tree("Devices", ("ID", "Driver", "In", "Out", "Rate", "Name"),
                                   (50, 130, 50, 50, 80, 600), extra="Rescan")
        self.track_tree = self._tree("Tracks", ("Track", "Length s", "Offset ms", "Effects on",
                                                "Est. CPU %"), (200, 90, 100, 380, 100))
        self._tab_load()
        self._tab_report()
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        theme.add_scale_listener(self._on_scale)

    # ---- UI scale (T016) ------------------------------------------------ #
    def _on_scale(self, scale):
        """Fonts and ttk metrics already follow ui_theme; fix the pixel sizes set at build time."""
        try:
            for tv, widths in self._tree_widths.items():
                for c, w in zip(self._tree_cols[tv], widths):
                    tv.column(c, width=theme.scaled(w))
            for lbl in self.card_labels.values():
                lbl.config(wraplength=theme.scaled(150))
            self.load_canvas.config(height=theme.scaled(200))
            self.draw_load()
        except tk.TclError:
            pass

    def destroy(self):
        theme.remove_scale_listener(self._on_scale)
        super().destroy()

    # ---- building ------------------------------------------------------ #
    def _tab_log(self):
        f = ttk.Frame(self.nb)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        self.nb.add(f, text=" Log ")
        chips = ttk.Frame(f)
        chips.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        ttk.Label(chips, text="Show level and above:").pack(side="left", padx=(0, 6))
        self.level_chips = {}
        for lv in dl.LEVELS:
            chip = tk.Radiobutton(chips, text=lv, value=lv, variable=self.level_var,
                                  indicatoron=False, command=self.rerender, bd=0, padx=10, pady=3,
                                  bg=theme.PALETTE["surface3"], fg=LEVEL_COLORS[lv],
                                  selectcolor="#245C3A", activebackground="#444444",
                                  activeforeground=LEVEL_COLORS[lv], font=theme.font("UI_BOLD"))
            chip.pack(side="left", padx=2)
            self.level_chips[lv] = chip
        self.pause_btn = ttk.Button(chips, text="PAUSE SCROLL", style="Neutral.TButton",
                                    command=self.toggle_autoscroll)
        self.pause_btn.pack(side="right", padx=2)
        self.clear_btn = ttk.Button(chips, text="CLEAR", style="Neutral.TButton",
                                    command=self.clear_log)
        self.clear_btn.pack(side="right", padx=2)
        t = tk.Text(f, height=4, bg="#0A0A0A", fg="#00FF66", insertbackground="white",
                    font=theme.font("MONO"), state="disabled", wrap="none")
        sb = ttk.Scrollbar(f, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        for lv, c in LEVEL_COLORS.items():
            t.tag_configure(lv, foreground=c)
        return t

    def _tab_engine(self):
        f = ttk.Frame(self.nb)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        self.nb.add(f, text=" Engine ")
        p = theme.PALETTE
        cards = ttk.Frame(f)
        cards.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        self.card_vars, self.card_labels = {}, {}
        for i, (key, caption) in enumerate(CARDS):
            cards.columnconfigure(i, weight=1, uniform="cards")
            box = tk.Frame(cards, bg=p["surface2"], padx=8, pady=6)
            box.grid(row=0, column=i, sticky="nsew", padx=3)
            tk.Label(box, text=caption, bg=p["surface2"], fg=p["muted"], font=theme.font("SMALL"),
                     anchor="w").pack(fill="x")
            var = tk.StringVar(value="-")
            lbl = tk.Label(box, textvariable=var, bg=p["surface2"], fg=p["text"],
                           font=theme.font("UI_BOLD"), anchor="w", justify="left", wraplength=theme.scaled(150))
            lbl.pack(fill="x")
            self.card_vars[key], self.card_labels[key] = var, lbl
        self.engine_tree = self._make_tree(f, ("Item", "Value"), (240, 700), row=1)

    def _tree(self, title, cols, widths, extra=None):
        f = ttk.Frame(self.nb)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self.nb.add(f, text=f" {title} ")
        tv = self._make_tree(f, cols, widths, row=0, sortable=True)
        if extra:
            ttk.Button(f, text=extra, style="Neutral.TButton", command=self.on_rescan).grid(
                row=0, column=2, sticky="n", padx=4)
        return tv

    def _make_tree(self, f, cols, widths, row, sortable=False):
        tv = ttk.Treeview(f, columns=cols, show="headings", height=1)
        sb = ttk.Scrollbar(f, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        self._tree_cols[tv] = tuple(cols)
        self._tree_widths[tv] = tuple(widths)
        widths = [theme.scaled(w) for w in widths]
        for c, w in zip(cols, widths):
            if sortable:
                tv.heading(c, text=c, command=lambda c=c, tv=tv: self.sort_by(tv, c))
            else:
                tv.heading(c, text=c)
            tv.column(c, width=w, anchor="w")
        tv.grid(row=row, column=0, sticky="nsew")
        sb.grid(row=row, column=1, sticky="ns")
        return tv

    def _tab_load(self):
        f = ttk.Frame(self.nb)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        self.nb.add(f, text=" Load ")
        self.load_lbl = ttk.Label(f, text="Mount the audio engine to see the callback time per block.",
                                  style="Muted.TLabel")
        self.load_lbl.grid(row=0, column=0, sticky="w", pady=(4, 4))
        self.load_canvas = tk.Canvas(f, bg="#0A0A0A", highlightthickness=0,
                                     height=theme.scaled(200))
        self.load_canvas.grid(row=1, column=0, sticky="nsew")
        self.load_canvas.bind("<Configure>", lambda e: self.draw_load())

    def _tab_report(self):
        f = ttk.Frame(self.nb)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        self.nb.add(f, text=" Report ")
        row = ttk.Frame(f)
        row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        ttk.Button(row, text="REFRESH REPORT", style="Neutral.TButton",
                   command=self.show_report).pack(side="left")
        ttk.Label(row, text="  This is the text COPY DEBUG REPORT puts on the clipboard.",
                  style="Muted.TLabel").pack(side="left")
        self.report_text = tk.Text(f, height=4, bg="#0A0A0A", fg="#CCCCCC", font=theme.font("MONO"),
                                   state="disabled", wrap="none")
        sb = ttk.Scrollbar(f, command=self.report_text.yview)
        self.report_text.configure(yscrollcommand=sb.set)
        self.report_text.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

    # ---- log tab ------------------------------------------------------- #
    def _append(self, rec):
        self.console.configure(state="normal")
        self.console.insert(tk.END, dl.format_record(rec) + "\n", rec[1])
        self._lines += 1
        if self._lines > MAX_LINES:
            self.console.delete("1.0", "2.0")
            self._lines -= 1
        if self.autoscroll_var.get():
            self.console.see(tk.END)
        self.console.configure(state="disabled")

    def _update_count(self):
        word = "matches" if self.search_var.get().strip() else "lines"
        self.match_lbl.config(text=f"{self._lines} {word}")

    def rerender(self):
        recs = [r for r in self.dlog.records(self.level_var.get(), self.search_var.get())
                if r[0] > self._clear_ts]
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")
        self._lines = 0
        for r in recs[-MAX_LINES:]:
            self._append(r)
        self._update_count()

    def pump(self):
        """Called by the app every 30 ms: move new log records to the screen."""
        self.dlog.drain_rt()
        n = 0
        lv, s = self.level_var.get(), self.search_var.get()
        while n < 200:
            try:
                rec = self.dlog.pending.get_nowait()
            except Exception:
                break
            n += 1
            if dl.filter_records([rec], lv, s):
                self._append(rec)
        if n:
            self._update_count()

    def toggle_autoscroll(self):
        self.autoscroll_var.set(not self.autoscroll_var.get())
        on = self.autoscroll_var.get()
        self.pause_btn.config(text="PAUSE SCROLL" if on else "RESUME SCROLL")
        if on:
            self.console.see(tk.END)

    def clear_log(self):
        """Empty the log view. The log file and the report still keep every line."""
        import time
        self._clear_ts = time.time()
        self.rerender()

    # ---- sorting ------------------------------------------------------- #
    def sort_by(self, tv, col):
        old_col, old_rev = self._sort.get(tv, (None, True))
        self._sort[tv] = (col, (not old_rev) if col == old_col else False)
        self._apply_sort(tv)

    def _apply_sort(self, tv):
        if tv not in self._sort:
            return
        col, rev = self._sort[tv]
        cols = self._tree_cols[tv]
        i = cols.index(col)
        rows = [tv.item(k, "values") for k in tv.get_children()]
        rows.sort(key=lambda r: _sort_key(r[i]), reverse=rev)
        tv.delete(*tv.get_children())
        for r in rows:
            tv.insert("", "end", values=r)
        for c in cols:
            mark = (" \u25BC" if rev else " \u25B2") if c == col else ""
            tv.heading(c, text=c + mark)

    # ---- other tabs ---------------------------------------------------- #
    def _tab_changed(self):
        if self.nb.index(self.nb.select()) == TAB_REPORT:
            self.show_report()
        self.refresh()

    def refresh(self):
        """Fill the visible tab (called every 500 ms and on tab change)."""
        tab = self.nb.index(self.nb.select())
        if tab == TAB_ENGINE:
            rows = dl.engine_snapshot(self.engine)
            rows[-1] = ("log queue (GUI)", self.dlog.pending.qsize())
            self._fill(self.engine_tree, rows)
            self.update_cards()
        elif tab == TAB_DEVICES:
            rows = [(r["id"], r["driver"], r["max_in"], r["max_out"],
                     f"{r['default_sr']:.0f}", r["name"]) for r in (self.get_device_rows() or [])]
            self._fill(self.dev_tree, rows)
        elif tab == TAB_TRACKS:
            cost = self.cost_provider() if self.cost_provider else None
            self._fill(self.track_tree, dl.tracks_snapshot(self.engine, cost))
        elif tab == TAB_LOAD:
            self.draw_load()

    def tick(self):
        """Called by the Debug tab from the app's 150 ms loop while it is visible (cheap)."""
        tab = self.nb.index(self.nb.select())
        if tab == TAB_ENGINE:
            self.update_cards()
        elif tab == TAB_LOAD:
            self.draw_load()

    def _fill(self, tv, rows):
        tv.delete(*tv.get_children())
        for r in rows:
            tv.insert("", "end", values=["-" if v is None else v for v in r])
        self._apply_sort(tv)

    def update_cards(self):
        e = self.engine
        tel = e.telemetry
        s = tel.summary()
        snap = dict(dl.engine_snapshot(e))
        rtt = e.measured_rtt_ms()
        vals = {"state": f"{snap['state']} / {snap['transport']}",
                "mode": str(snap["mode"]),
                "cpu": f"{s['cpu_avg_pct']} % (peak {s['cpu_peak_pct']} %)",
                "rtt": f"{rtt:.1f} ms measured" if rtt is not None else f"{snap['reported latency (ms)']} ms reported",
                "drops": f"{tel.xruns} card, {tel.overruns} late",
                "split": dl.split_text(e),
                "blocks": str(s["blocks"]),
                "peak": snap["peak L / R / in"]}
        for k, v in vals.items():
            if self.card_vars[k].get() != v:
                self.card_vars[k].set(v)
        p = theme.PALETTE
        bad = s["cpu_avg_pct"] > 70
        self.card_labels["cpu"].config(fg=p["error"] if bad else p["accent"])
        self.card_labels["drops"].config(fg=p["error"] if (tel.xruns or tel.overruns) else p["text"])
        st = e.split_stats() if hasattr(e, "split_stats") else None
        self.card_labels["split"].config(fg=p["error"] if (st and st["underflows"]) else p["text"])
        self.card_labels["state"].config(fg=p["accent"] if e.is_active else p["muted"])

    def draw_load(self):
        """Callback time per block (last 100 blocks). Full height = 150 % of the block time;
        the red line is 100 % (the block time). Bars above 70 % are red."""
        c = self.load_canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        tel = self.engine.telemetry
        pad_l, pad_b = theme.scaled(46), theme.scaled(4)
        gh = h - pad_b - 4
        c.create_rectangle(pad_l, 2, w - 3, h - pad_b, outline="#333333")
        for frac, label in ((0.0, "0 %"), (0.5, "50 %"), (1.0, "100 %"), (1.5, "150 %")):
            y = (h - pad_b) - (frac / 1.5) * gh
            col = "#FF3333" if frac == 1.0 else "#555555"
            c.create_line(pad_l, y, w - 3, y, fill=col, dash=() if frac == 1.0 else (2, 4))
            c.create_text(pad_l - 4, y, text=label, anchor="e", fill=col, font=theme.font("SMALL"))
        if not tel.block_s:
            self.load_lbl.config(text="Mount the audio engine to see the callback time per block.")
            return
        loads = tel.history_loads()
        n = len(loads)
        bar_w = max(1.0, (w - pad_l - 4) / float(n))
        for i, v in enumerate(loads):
            if v <= 0:
                continue
            bh = min(gh, (v / 1.5) * gh)
            x0 = pad_l + 1 + i * bar_w
            c.create_rectangle(x0, (h - pad_b) - bh, x0 + bar_w, h - pad_b - 1,
                               fill="#FF3333" if v > 0.7 else "#00AA55", outline="")
        s = tel.summary()
        self.load_lbl.config(
            text=f"block {s['block_ms']} ms | last {s['last_ms']} ms | avg {s['avg_ms']} ms | "
                 f"worst {s['max_ms']} ms | late blocks {s['overruns']}   (red line = block time)")

    def show_report(self):
        text = dl.build_report(self.engine, self.get_settings(), self.dlog,
                               device_rows=self.get_device_rows())
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", text)
        self.report_text.configure(state="disabled")
        return text

    # ---- actions ------------------------------------------------------- #
    def copy_report(self):
        text = dl.build_report(self.engine, self.get_settings(), self.dlog,
                               device_rows=self.get_device_rows())
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            copied = True
        except Exception:
            copied = False
        try:
            path = dl.save_report(text, self.dlog.log_dir)
        except Exception as e:
            path = None
            self.dlog.add(f"Could not save report file: {e}", "WARN")
        self.dlog.add("Debug report " + ("copied to the clipboard" if copied else "NOT copied")
                      + (f" and saved: {path}" if path else "."), "SUCCESS" if copied else "WARN")
        return text

    def toggle_test_bar(self):
        if self.test_bar.winfo_ismapped():
            if self.engine.test_signal_name:
                self.toggle_test()
            self.test_bar.grid_remove()
        else:
            self.test_bar.grid(row=1, column=0, sticky="ew", pady=(0, 4))

    def toggle_test(self):
        if self.engine.test_signal_name:
            self.engine.set_test_signal(None)
            self.test_btn.config(text="START")
        elif not self.engine.is_active:
            self.dlog.add("Mount the audio engine before using the test signal.", "WARN")
        else:
            self.engine.set_test_signal(self.test_kind.get())
            self.test_btn.config(text="STOP")
