"""
tab_lab.py  (Phase 10 / T021)
The Lab tab: record a raw sound card capture (T020), analyze it (T019) and read the verdict
without leaving the app.

    1. pick a test type, a duration and a label, press START CAPTURE (STOP ends it early)
    2. press ANALYZE: crackle_report.run() works in a background thread (never on the Tk thread)
    3. the verdict, the evidence lines and report.png appear in the tab; OPEN FOLDER shows the
       pack (analysis_pack.zip is the file to attach to a Claude chat)

Captures live in `captures/<YYYYMMDD_HHMMSS>_<label>/` next to main.py (never in the zip).
The engine has no tone generator, so the two tone test types play a looping 1 kHz sine Track
through the engine and remove it again on STOP (it shows in the Mixer tab meanwhile).
Everything that does not need Tk (folder names, the capture list, the tone buffer, the evidence
text) is a plain function so tests can check it directly.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import numpy as np

import ui_theme as theme
from scroll_frame import ScrollableFrame
from tabs import BaseTab, panelize

CAPTURES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
TONE_HZ = 1000.0
TONE_LEVEL = 0.3
MIN_SECONDS, MAX_SECONDS, DEFAULT_SECONDS = 5, 120, 20
NOT_MOUNTED_HINT = "Mount the audio engine in the Audio tab first (MOUNT AUDIO ENGINE)."

# key, name, what to do, plays the tone, nothing is played into the input
TEST_TYPES = (
    {"key": "silent", "name": "Silent input", "tone": False, "silent": True,
     "help": "Nothing plugged in, or the source muted / the input shorted. Shows the noise and "
             "clicks of the card and the driver alone."},
    {"key": "tone_cable", "name": "Test tone (cable out -> in)", "tone": True, "silent": False,
     "help": "Plug a cable from the output to the input. A 1 kHz tone is played and recorded "
             "back; any click in it comes from the card, driver or timing."},
    {"key": "live", "name": "Live source", "tone": False, "silent": False,
     "help": "Play music or your instrument into the input (a phone into line-in works). "
             "Monitoring is switched off during the capture."},
    {"key": "playback", "name": "Playback only", "tone": True, "silent": True,
     "help": "A 1 kHz tone is played, the input stays unplugged. The timing of every audio "
             "block is recorded; the input is ignored."},
)
TYPE_BY_NAME = {t["name"]: t for t in TEST_TYPES}
TYPE_BY_KEY = {t["key"]: t for t in TEST_TYPES}


# --------------------------------------------------------------------------- plain helpers
def safe_label(label):
    """Keep only [A-Za-z0-9_-]; spaces become '-'. Never empty."""
    s = re.sub(r"[^A-Za-z0-9_-]", "", str(label or "").strip().replace(" ", "-"))
    return s[:40] or "capture"


def make_capture_folder(root, label, now=None):
    """Path (not created) `<root>/<YYYYMMDD_HHMMSS>_<label>`; a numeric suffix keeps it unique."""
    now = now or datetime.now()
    base = os.path.join(root, "%s_%s" % (now.strftime("%Y%m%d_%H%M%S"), safe_label(label)))
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = "%s_%d" % (base, n)
    return path


def tone_buffer(sample_rate):
    """One second of a 1 kHz sine. One second holds a whole number of cycles at 44100 and 48000
    Hz, so it loops without a click."""
    n = int(sample_rate)
    t = np.arange(n, dtype=np.float64) / float(sample_rate)
    return (TONE_LEVEL * np.sin(2.0 * np.pi * TONE_HZ * t)).astype(np.float32)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def analysis_dir(folder):
    return os.path.join(folder, "analysis")


def list_captures(root):
    """Capture folders under `root`, newest first. Each row: folder, name, date, label, type,
    seconds, analyzed (analysis/report.json exists)."""
    rows = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return rows
    for name in names:
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        meta = read_json(os.path.join(folder, "meta.json"))
        if meta is None and not os.path.exists(os.path.join(folder, "raw.wav")):
            continue                       # not a capture folder (for example a matrix folder)
        meta = meta or {}
        m = re.match(r"^(\d{8})_(\d{6})_?(.*)$", name)
        if m:
            try:
                date = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                date = "-"
            rest = m.group(3)
        else:
            date, rest = "-", name
        rows.append({"folder": folder, "name": name, "date": date,
                     "label": str(meta.get("label") or rest or name),
                     "type": str(meta.get("test_type_name") or "-"),
                     "seconds": meta.get("seconds"),
                     "analyzed": os.path.exists(os.path.join(analysis_dir(folder), "report.json"))})
    rows.sort(key=lambda r: r["name"], reverse=True)
    return rows


def evidence_lines(verdict, limit=8):
    """Evidence of the top hypothesis, then its next test, as a list of text lines."""
    lines = []
    hyps = (verdict or {}).get("hypotheses") or []
    if hyps:
        for e in (hyps[0].get("evidence") or [])[:limit]:
            lines.append("- " + str(e))
        nxt = hyps[0].get("next_test")
        if nxt:
            lines.append("")
            lines.append("Next test: " + str(nxt))
    for n in ((verdict or {}).get("notes") or [])[:4]:
        lines.append("Note: " + str(n))
    return lines


def counts_line(report):
    c = (report or {}).get("counts") or {}
    if not c:
        return ""
    return "Clicks: %s (%.1f per minute)   Dropouts: %s   Clipped runs: %s" % (
        c.get("clicks", "?"), float(c.get("clicks_per_min", 0.0)), c.get("dropouts", "?"),
        c.get("clip_runs", "?"))


def open_folder(path):
    """Show a folder in the file manager (Explorer, Finder or xdg-open). Tests patch this."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)                                  # noqa: B606 (Windows only)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def load_photo(path, max_w, max_h):
    """A Tk image of the PNG shrunk to fit max_w x max_h: Pillow when installed, else Tk's own
    integer subsampling. None when the file cannot be read."""
    try:
        from PIL import Image, ImageTk
        im = Image.open(path)
        im.thumbnail((max(1, int(max_w)), max(1, int(max_h))))
        return ImageTk.PhotoImage(im)
    except ImportError:
        pass
    except Exception:
        return None
    try:
        img = tk.PhotoImage(file=path)
        k = max(1, -(-img.width() // max(1, int(max_w))), -(-img.height() // max(1, int(max_h))))
        return img.subsample(k, k) if k > 1 else img
    except tk.TclError:
        return None


# --------------------------------------------------------------------------- the tab
class Tab(BaseTab):
    title = "Lab"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.captures_root = CAPTURES_ROOT
        self.state = "idle"                  # idle | capturing | analyzing
        self._rec = None
        self._cap = None                     # dict about the running capture
        self._saved = None                   # engine state to put back on STOP
        self._tone_track = None
        self._after_id = None
        self._thread = None
        self._done = None                    # set by the worker: ("ok", result) or ("err", text)
        self._target = None                  # capture folder ANALYZE works on
        self._last_folder = None
        self._photo = None
        self._image_path = None
        self._rows = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.scroll = ScrollableFrame(self, vertical=True, horizontal=False)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        body = self.scroll.body
        body.columnconfigure(0, weight=1, uniform="lab")
        body.columnconfigure(1, weight=1, uniform="lab")

        self.capture_box = self._build_capture(body)
        self.capture_box.grid(row=0, column=0, padx=(16, 8), pady=8, sticky="new")
        self.list_box = self._build_list(body)
        self.list_box.grid(row=0, column=1, padx=(8, 16), pady=8, sticky="new")
        self.result_box = self._build_result(body)
        self.result_box.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="new")
        for box in (self.capture_box, self.list_box, self.result_box):
            panelize(box)

        self.refresh_list()
        self._update_buttons()
        theme.add_scale_listener(self._on_scale)
        self.bind("<Destroy>", self._on_destroy_event, add="+")

    # ------------------------------------------------------------------ building
    def _build_capture(self, parent):
        p = theme.PALETTE
        box = ttk.LabelFrame(parent, text=" CAPTURE ", padding=12)
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="Test type", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        self.type_var = tk.StringVar(value=TEST_TYPES[0]["name"])
        self.type_box = ttk.Combobox(box, textvariable=self.type_var, state="readonly",
                                     values=[t["name"] for t in TEST_TYPES])
        self.type_box.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=3)
        self.type_box.bind("<<ComboboxSelected>>", lambda e: self._on_type())
        self.help_lbl = tk.Label(box, text="", bg=p["surface1"], fg=p["muted"], font=theme.font("SMALL"),
                                 anchor="w", justify="left", wraplength=theme.scaled(420))
        self.help_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(box, text="Duration (s)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        self.seconds_var = tk.IntVar(value=DEFAULT_SECONDS)
        self.seconds_spin = tk.Spinbox(box, from_=MIN_SECONDS, to=MAX_SECONDS, width=6,
                                       textvariable=self.seconds_var, font=theme.font("UI"),
                                       bg=p["surface2"], fg=p["text"], insertbackground=p["text"],
                                       buttonbackground=p["surface3"], relief="flat")
        self.seconds_spin.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=3)
        ttk.Label(box, text="Label", style="Panel.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        self.label_var = tk.StringVar(value="test")
        self.label_entry = tk.Entry(box, textvariable=self.label_var, font=theme.font("UI"),
                                    bg=p["surface2"], fg=p["text"], insertbackground=p["text"], relief="flat")
        self.label_entry.grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=3)

        btns = ttk.Frame(box, style="Panel.TFrame")
        btns.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self.start_btn = ttk.Button(btns, text="START CAPTURE", style="Action.TButton", command=self.start_capture)
        self.start_btn.grid(row=0, column=0, padx=(0, 8))
        self.stop_btn = ttk.Button(btns, text="STOP", style="Stop.TButton", command=self.stop_capture)
        self.stop_btn.grid(row=0, column=1)

        self.cap_progress = ttk.Progressbar(box, orient="horizontal", mode="determinate",
                                            length=theme.scaled(300), maximum=100)
        self.cap_progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        self.status_var = tk.StringVar(value="")
        tk.Label(box, textvariable=self.status_var, bg=p["surface1"], fg=p["text"], font=theme.font("MONO"),
                 anchor="w", justify="left", wraplength=theme.scaled(420)).grid(row=6, column=0, columnspan=2, sticky="w")
        self.hint_var = tk.StringVar(value="")
        self.hint_lbl = tk.Label(box, textvariable=self.hint_var, bg=p["surface1"], fg=p["warn"],
                                 font=theme.font("SMALL"), anchor="w", justify="left", wraplength=theme.scaled(420))
        self.hint_lbl.grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._on_type()
        return box

    def _build_list(self, parent):
        box = ttk.LabelFrame(parent, text=" EARLIER CAPTURES ", padding=12)
        box.columnconfigure(0, weight=1)
        cols = ("date", "label", "type", "seconds", "analyzed")
        self.table = ttk.Treeview(box, columns=cols, show="headings", height=7, selectmode="browse")
        for key, text, w in (("date", "Date", 160), ("label", "Label", 100), ("type", "Type", 150),
                             ("seconds", "Sec", 50), ("analyzed", "Analyzed", 85)):
            self.table.heading(key, text=text)
            self.table.column(key, width=w, anchor="w", stretch=key in ("label", "type"))
        self.table.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.table.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=sb.set)
        self.table.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.refresh_btn = ttk.Button(box, text="REFRESH", style="Neutral.TButton", command=self.refresh_list)
        self.refresh_btn.grid(row=1, column=0, sticky="w", pady=(8, 0))
        return box

    def _build_result(self, parent):
        p = theme.PALETTE
        box = ttk.LabelFrame(parent, text=" ANALYSIS ", padding=12)
        box.columnconfigure(0, weight=1)
        btns = ttk.Frame(box, style="Panel.TFrame")
        btns.grid(row=0, column=0, sticky="w")
        self.analyze_btn = ttk.Button(btns, text="ANALYZE", style="Action.TButton", command=self.analyze)
        self.analyze_btn.grid(row=0, column=0, padx=(0, 8))
        self.open_btn = ttk.Button(btns, text="OPEN FOLDER", style="Neutral.TButton", command=self.open_target_folder)
        self.open_btn.grid(row=0, column=1)
        self.target_var = tk.StringVar(value="No capture selected.")
        tk.Label(box, textvariable=self.target_var, bg=p["surface1"], fg=p["muted"], font=theme.font("SMALL"),
                 anchor="w").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.an_progress = ttk.Progressbar(box, orient="horizontal", mode="indeterminate", length=theme.scaled(300))
        self.an_progress.grid(row=2, column=0, sticky="ew", pady=(6, 2))
        self.verdict_var = tk.StringVar(value="")
        self.verdict_lbl = tk.Label(box, textvariable=self.verdict_var, bg=p["surface1"], fg=p["text"],
                                    font=theme.font("UI_BOLD"), anchor="w", justify="left",
                                    wraplength=theme.scaled(900))
        self.verdict_lbl.grid(row=3, column=0, sticky="w", pady=(6, 2))
        self.counts_var = tk.StringVar(value="")
        tk.Label(box, textvariable=self.counts_var, bg=p["surface1"], fg=p["muted"], font=theme.font("MONO"),
                 anchor="w").grid(row=4, column=0, sticky="w")
        self.evidence = tk.Text(box, height=9, wrap="word", font=theme.font("MONO"), bg=p["surface2"],
                                fg=p["text"], relief="flat", state="disabled")
        self.evidence.grid(row=5, column=0, sticky="ew", pady=(6, 6))
        self.image_lbl = tk.Label(box, bg=p["surface1"], text="", fg=p["muted"], font=theme.font("SMALL"))
        self.image_lbl.grid(row=6, column=0, sticky="w")
        return box

    # ------------------------------------------------------------------ scale / destroy
    def _on_scale(self, scale):
        try:
            self.cap_progress.config(length=theme.scaled(300))
            self.an_progress.config(length=theme.scaled(300))
            self.help_lbl.config(wraplength=theme.scaled(420))
            self.hint_lbl.config(wraplength=theme.scaled(420))
            self.verdict_lbl.config(wraplength=theme.scaled(900))
            if self._image_path:
                self._show_image(self._image_path)
        except tk.TclError:
            pass

    def _cancel_timer(self):
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _on_destroy_event(self, event):
        if str(event.widget) == str(self):
            self._cancel_timer()

    def destroy(self):
        self._cancel_timer()
        theme.remove_scale_listener(self._on_scale)
        if self.state == "capturing":
            try:
                self.app.engine.stop_capture()
                self._finish_engine()
            except Exception:
                pass
            self.state = "idle"
        super().destroy()

    # ------------------------------------------------------------------ small UI helpers
    def _on_type(self):
        t = TYPE_BY_NAME.get(self.type_var.get(), TEST_TYPES[0])
        self.help_lbl.config(text=t["help"])

    def _engine_ready(self):
        e = self.app.engine
        return bool(getattr(e, "is_active", False))

    def _update_buttons(self):
        ready = self._engine_ready()
        idle = self.state == "idle"
        capturing = self.state == "capturing"
        self.start_btn.state(["!disabled"] if (idle and ready) else ["disabled"])
        self.stop_btn.state(["!disabled"] if capturing else ["disabled"])
        for w in (self.type_box,):
            w.state(["!disabled"] if idle else ["disabled"])
        for w in (self.seconds_spin, self.label_entry):
            w.config(state="normal" if idle else "disabled")
        can_an = idle and bool(self._target) and os.path.isdir(self._target or "")
        self.analyze_btn.state(["!disabled"] if can_an else ["disabled"])
        self.open_btn.state(["!disabled"] if (self._target and self.state != "capturing") else ["disabled"])
        self.refresh_btn.state(["!disabled"] if self.state != "capturing" else ["disabled"])
        if not ready and idle:
            self.hint_var.set(NOT_MOUNTED_HINT)
        elif capturing and self._cap and self._cap["type"]["tone"] and not self._cap["type"]["silent"]:
            self.hint_var.set("Keep the cable from the output to the input plugged in.")
        else:
            self.hint_var.set("")

    def on_show(self):
        self.refresh_list()
        self._update_buttons()

    def on_tick(self):
        self._update_buttons()

    def _schedule(self):
        if self._after_id is None and self.state in ("capturing", "analyzing"):
            try:
                self._after_id = self.after(100, self._tick)
            except tk.TclError:
                self._after_id = None

    def _tick(self):
        self._after_id = None
        if self.state == "capturing":
            rec = self._rec
            secs = rec.seconds if rec is not None else 0.0
            total = float(self._cap["seconds"])
            self.cap_progress.config(value=min(100.0, 100.0 * secs / max(total, 0.001)))
            self.status_var.set("Capturing: %.1f / %d s" % (secs, int(total)))
            if rec is None or getattr(rec, "full", False) or secs >= total:
                self.stop_capture()
        elif self.state == "analyzing":
            if self._done is not None:
                self._finish_analysis()
        self._schedule()

    # ------------------------------------------------------------------ the capture list
    def refresh_list(self):
        keep = self._target
        self.table.delete(*self.table.get_children())
        self._rows = {}
        for r in list_captures(self.captures_root):
            sec = r["seconds"]
            iid = self.table.insert("", "end", values=(
                r["date"], r["label"], r["type"], "%.1f" % sec if isinstance(sec, (int, float)) else "-",
                "yes" if r["analyzed"] else "no"))
            self._rows[iid] = r
            if keep and os.path.abspath(r["folder"]) == os.path.abspath(keep):
                self.table.selection_set(iid)
        self._update_buttons()

    def _on_select(self):
        sel = self.table.selection()
        if not sel or sel[0] not in self._rows or self.state != "idle":
            return
        self._set_target(self._rows[sel[0]]["folder"])
        rep = read_json(os.path.join(analysis_dir(self._target), "report.json"))
        if rep:
            self._show_report(rep, analysis_dir(self._target))
        else:
            self._clear_result()

    def _set_target(self, folder):
        self._target = folder
        self.target_var.set("Selected: " + os.path.basename(folder) if folder else "No capture selected.")
        self._update_buttons()

    # ------------------------------------------------------------------ capture
    def start_capture(self):
        if self.state != "idle":
            return
        engine = self.app.engine
        if not self._engine_ready():
            self.status_var.set(NOT_MOUNTED_HINT)
            return
        if getattr(engine, "capture", None) is not None:
            self.status_var.set("A capture is already running.")
            return
        t = TYPE_BY_NAME.get(self.type_var.get(), TEST_TYPES[0])
        try:
            seconds = int(self.seconds_var.get())
        except (tk.TclError, ValueError):
            seconds = DEFAULT_SECONDS
        seconds = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
        self.seconds_var.set(seconds)
        label = safe_label(self.label_var.get())
        self.label_var.set(label)
        folder = make_capture_folder(self.captures_root, label)

        self._saved = {"monitor": bool(engine.input_monitor_enabled),
                       "monitor_var": bool(self.app.monitor_var.get()),
                       "playing": bool(engine.is_playing), "playhead": int(engine.playhead)}
        engine.input_monitor_enabled = False           # monitoring is off in every test type
        self.app.monitor_var.set(False)
        self._tone_track = None
        try:
            if t["tone"]:
                from track import Track
                tr = Track("LAB TONE", engine.sample_rate)
                tr.load_from_array(tone_buffer(engine.sample_rate), 0)
                tr.loop_enabled = True
                self._tone_track = tr
                engine.add_track(tr)
                engine.set_playhead_seconds(0)
                engine.play()
            self._split0 = engine.split_stats() if hasattr(engine, "split_stats") else None
            self._rec = engine.start_capture(max_seconds=seconds, capture_output=bool(t["tone"]))
        except Exception as e:                          # keep the engine as it was
            self._finish_engine()
            self.status_var.set("Could not start the capture: %s" % e)
            return
        self._cap = {"type": t, "seconds": seconds, "label": label, "folder": folder, "t0": time.time()}
        self.state = "capturing"
        self.cap_progress.config(value=0)
        self.status_var.set("Capturing: 0.0 / %d s" % seconds)
        self._clear_result()
        self._update_buttons()
        self._schedule()

    def _finish_engine(self):
        """Put the engine back as it was before START (tone track, transport, monitoring)."""
        engine = self.app.engine
        if self._tone_track is not None:
            try:
                engine.remove_track(self._tone_track)
            except Exception:
                pass
            self._tone_track = None
        saved, self._saved = self._saved, None
        if saved:
            if not saved["playing"]:
                engine.stop()
            engine.set_playhead_seconds(saved["playhead"] / float(engine.sample_rate))
            engine.input_monitor_enabled = saved["monitor"]
            try:
                self.app.monitor_var.set(saved["monitor_var"])
            except tk.TclError:
                pass

    def stop_capture(self):
        if self.state != "capturing":
            return
        engine = self.app.engine
        cap = self._cap
        t = cap["type"]
        rec = engine.stop_capture() or self._rec
        self._rec = None
        self._finish_engine()
        self.state = "idle"
        self._cancel_timer()
        self.cap_progress.config(value=0)
        try:
            meta = {"label": cap["label"], "test_type": t["key"], "test_type_name": t["name"],
                    "source": "raw", "effects_off": True, "monitoring_off": True,
                    "silent_input": bool(t["silent"]), "engine_mode": str(engine.mode_name),
                    "requested_seconds": cap["seconds"], "app": "Live Looper Pro"}
            from split_stream import split_meta
            meta.update(split_meta(getattr(self, "_split0", None),
                                   engine.split_stats() if hasattr(engine, "split_stats") else None))
            if t["tone"]:
                meta.update({"tone_hz": TONE_HZ, "tone_level": TONE_LEVEL})
            rec.to_files(cap["folder"], extra_meta=meta)
            flagged = int(np.count_nonzero(rec.b_status[:rec.n_blocks]))
            self.status_var.set("Saved %.1f s, %d blocks, %d with sound card status flags.\n%s" % (
                rec.seconds, rec.n_blocks, flagged, os.path.basename(cap["folder"])))
            self._last_folder = cap["folder"]
            self._target = cap["folder"]
        except Exception as e:
            self.status_var.set("Could not save the capture: %s" % e)
            self._cap = None
            self._update_buttons()
            return
        self._cap = None
        self.refresh_list()
        self._set_target(self._last_folder)

    # ------------------------------------------------------------------ analysis
    def analyze(self):
        if self.state != "idle" or not self._target or not os.path.isdir(self._target):
            return
        folder = self._target
        self.state = "analyzing"
        self._done = None
        self._clear_result()
        self.verdict_var.set("Analyzing %s ..." % os.path.basename(folder))
        self.an_progress.start(15)
        self._update_buttons()
        self._thread = threading.Thread(target=self._worker, args=(folder,), daemon=True)
        self._thread.start()
        self._schedule()

    def _worker(self, folder):
        """Runs off the Tk thread. Touches no widget; only sets self._done."""
        try:
            import crackle_report                       # lazy: keeps startup cheap
            meta = read_json(os.path.join(folder, "meta.json")) or {}
            res = crackle_report.run(
                folder, out_dir=analysis_dir(folder),
                effects="off" if meta.get("effects_off") else None,
                monitoring="off" if meta.get("monitoring_off") else None,
                silent_input=True if meta.get("silent_input") else None)
            self._done = ("ok", res)
        except Exception as e:                          # report the problem in the tab
            self._done = ("err", "%s: %s" % (type(e).__name__, e))

    def _finish_analysis(self):
        kind, payload = self._done
        self._done = None
        self._thread = None
        self.an_progress.stop()
        self.state = "idle"
        if kind == "ok":
            self._show_report(payload["report"], payload["out_dir"])
            self.refresh_list()
        else:
            self._clear_result()
            self.verdict_var.set("Analysis failed: " + payload)
        self._update_buttons()

    # ------------------------------------------------------------------ showing a result
    def _clear_result(self):
        self.verdict_var.set("")
        self.counts_var.set("")
        self._set_evidence([])
        self._image_path = None
        self._photo = None
        self.image_lbl.config(image="", text="")

    def _set_evidence(self, lines):
        self.evidence.config(state="normal")
        self.evidence.delete("1.0", "end")
        self.evidence.insert("1.0", "\n".join(lines))
        self.evidence.config(state="disabled")

    def _show_report(self, report, out_dir):
        v = report.get("verdict") or {}
        top = v.get("top", "?")
        self.verdict_var.set("Verdict: %s (confidence %s)\n%s" % (top, v.get("confidence", "?"), v.get("summary", "")))
        self.counts_var.set(counts_line(report))
        self._set_evidence(evidence_lines(v))
        png = os.path.join(out_dir, "report.png")
        if os.path.exists(png):
            self._show_image(png)
        else:
            self._image_path = None
            self.image_lbl.config(image="", text="(no picture: matplotlib is not installed)")

    def _show_image(self, path):
        photo = load_photo(path, theme.scaled(900), theme.scaled(420))
        if photo is None:
            self.image_lbl.config(image="", text="(could not read report.png)")
            return
        self._photo = photo                              # keep a reference or Tk drops it
        self._image_path = path
        self.image_lbl.config(image=photo, text="")

    def open_target_folder(self):
        if not self._target:
            return
        an = analysis_dir(self._target)
        open_folder(an if os.path.isdir(an) else self._target)
