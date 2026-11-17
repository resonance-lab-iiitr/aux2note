"""
fx_dialog.py
A per-track "effects rack" window: full equalizer, compressor, distortion,
delay/echo and reverb, all editable live while the engine keeps running.

UX fix: every effect (other than EQ) starts life with `enabled = False`, and
previously the only way to actually hear a change was to separately notice
and tick the small "X Enabled" checkbox above the sliders. Moving a knob and
hearing nothing is the single most common "this feels broken" complaint for
this kind of rack, so now touching ANY slider for an effect automatically
enables it (and ticks its checkbox to match) - the checkbox still lets you
switch an effect off again without losing its settings.
"""

import tkinter as tk
from tkinter import ttk
from effects import benchmark_costs


class FxDialog(tk.Toplevel):
    # Track-id (or "__master__") -> currently open FxDialog instance, so
    # opening FX on a track that already has its rack open focuses the
    # existing window instead of spawning a confusing duplicate with two
    # sets of sliders fighting over the same effect state.
    _open_dialogs = {}

    def __init__(self, master, track, key=None, title=None):
        super().__init__(master)
        self.track = track
        self.title(title or f"FX Rack - {track.name}")
        self.configure(bg="#121212")
        self.geometry("480x660")
        self.resizable(False, False)

        self._key = key if key is not None else track
        FxDialog._open_dialogs[self._key] = self
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        try:    # quick benchmark, well under 0.2 s
            self._costs = benchmark_costs(self.track.effects.sample_rate, 64, reps=40)
        except Exception:
            self._costs = {}

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_eq_tab(nb)
        self._build_comp_tab(nb)
        self._build_dist_tab(nb)
        self._build_delay_tab(nb)
        self._build_reverb_tab(nb)

        hint = tk.Label(self, text="Tip: moving any slider below auto-enables that effect.",
                         bg="#121212", fg="#666666", font=("Segoe UI", 8, "italic"))
        hint.pack(pady=(0, 6))

    @classmethod
    def open_for(cls, master, track, key=None, title=None):
        """Open (or focus) the FX rack for `track`/`key`, never duplicating."""
        existing = cls._open_dialogs.get(key if key is not None else track)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        return cls(master, track, key=key, title=title)

    def _on_close(self):
        FxDialog._open_dialogs.pop(self._key, None)
        self.destroy()

    def _after_param_change(self):
        """Hook called after any parameter write; subclasses (Master FX)
        override to mirror settings into the mirror (R) channel chain."""
        pass

    # ------------------------------------------------------------------ #
    def _slider(self, parent, label, frm, to, get, set_, resolution=0.01, row=0,
                enable_var=None, effect=None):
        tk.Label(parent, text=label, bg="#1E1E1E", fg="#CCCCCC", font=("Segoe UI", 9)
                 ).grid(row=row, column=0, sticky="w", padx=6, pady=4)

        def on_move(v):
            set_(float(v))
            if effect is not None and enable_var is not None and not effect.enabled:
                effect.enabled = True
                enable_var.set(True)
            self._after_param_change()

        s = tk.Scale(parent, from_=frm, to=to, resolution=resolution, orient="horizontal",
                     bg="#1E1E1E", fg="#00FF66", troughcolor="#2A2A2A", highlightthickness=0,
                     length=260, command=on_move)
        s.set(get())
        s.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        return s

    def _check(self, parent, label, get, set_, row=0, col=0):
        var = tk.BooleanVar(value=get())

        def cb():
            set_(var.get())
            self._after_param_change()

        tk.Checkbutton(parent, text=label, variable=var, command=cb, bg="#121212",
                        activebackground="#121212", selectcolor="#2A2A2A", fg="#00FF66",
                        font=("Segoe UI", 9, "bold")).grid(row=row, column=col, sticky="w", padx=6, pady=6)
        return var

    def _reset_button(self, parent, row, col, reset_fn):
        def do_reset():
            reset_fn()
            self._after_param_change()
            self._on_close()
            # Reopen fresh so every slider re-reads the just-reset values.
            FxDialog.open_for(self.master, self.track, key=self._key, title=self.title())

        ttk.Button(parent, text="Reset to default", command=do_reset).grid(
            row=row, column=col, sticky="e", padx=6, pady=(10, 4))

    # ------------------------------------------------------------------ #
    def _cost_label(self, frame, key):
        """Small grey 'CPU cost' line at the bottom of an effect tab."""
        pct = self._costs.get(key)
        if pct is None:
            return
        tk.Label(frame, text=f"CPU cost: about {pct:.1f}% of one audio block (block 64)",
                 bg="#121212", fg="#666666", font=("Segoe UI", 8)
                 ).grid(row=9, column=0, columnspan=2, sticky="w", padx=6, pady=(14, 2))

    def _build_eq_tab(self, nb):
        frame = tk.Frame(nb, bg="#121212")
        nb.add(frame, text="Equalizer")
        self._cost_label(frame, "EQ (5 band)")

        eq = self.track.effects.eq
        eq_var = self._check(frame, "EQ Enabled", lambda: eq.enabled, lambda v: setattr(eq, "enabled", v), row=0)

        for i, band in enumerate(eq.bands):
            row_frame = tk.Frame(frame, bg="#1E1E1E")
            row_frame.grid(row=i + 1, column=0, columnspan=2, sticky="ew", padx=6, pady=3)
            self._slider(row_frame, f"{band.freq:>5.0f} Hz gain (dB)", -12.0, 12.0,
                         lambda b=band: b.gain_db, lambda v, b=band: b.set_gain(v), row=0,
                         enable_var=eq_var, effect=eq)

        def reset():
            eq.enabled = True
            for band in eq.bands:
                band.set_gain(0.0)
        self._reset_button(frame, row=len(eq.bands) + 1, col=1, reset_fn=reset)

    def _build_comp_tab(self, nb):
        frame = tk.Frame(nb, bg="#121212")
        nb.add(frame, text="Compressor")
        self._cost_label(frame, "Compressor")
        c = self.track.effects.compressor
        c_var = self._check(frame, "Compressor Enabled", lambda: c.enabled, lambda v: setattr(c, "enabled", v), row=0)
        self._slider(frame, "Threshold (dB)", -60.0, 0.0, lambda: c.threshold_db,
                     lambda v: setattr(c, "threshold_db", v), row=1, enable_var=c_var, effect=c)
        self._slider(frame, "Ratio", 1.0, 20.0, lambda: c.ratio, lambda v: setattr(c, "ratio", v),
                     row=2, enable_var=c_var, effect=c)
        self._slider(frame, "Attack (ms)", 0.5, 100.0, lambda: c.attack_ms,
                     lambda v: setattr(c, "attack_ms", v), row=3, enable_var=c_var, effect=c)
        self._slider(frame, "Release (ms)", 20.0, 1000.0, lambda: c.release_ms,
                     lambda v: setattr(c, "release_ms", v), row=4, enable_var=c_var, effect=c)
        self._slider(frame, "Makeup Gain (dB)", 0.0, 24.0, lambda: c.makeup_db,
                     lambda v: setattr(c, "makeup_db", v), row=5, enable_var=c_var, effect=c)

        def reset():
            c.enabled = False
            c.threshold_db, c.ratio, c.attack_ms, c.release_ms, c.makeup_db = -18.0, 3.0, 8.0, 120.0, 0.0
        self._reset_button(frame, row=6, col=1, reset_fn=reset)

    def _build_dist_tab(self, nb):
        frame = tk.Frame(nb, bg="#121212")
        nb.add(frame, text="Distortion")
        self._cost_label(frame, "Distortion")
        d = self.track.effects.distortion
        d_var = self._check(frame, "Distortion Enabled", lambda: d.enabled, lambda v: setattr(d, "enabled", v), row=0)
        self._slider(frame, "Drive", 0.0, 1.0, lambda: d.drive, lambda v: setattr(d, "drive", v),
                     row=1, enable_var=d_var, effect=d)
        self._slider(frame, "Mix", 0.0, 1.0, lambda: d.mix, lambda v: setattr(d, "mix", v),
                     row=2, enable_var=d_var, effect=d)

        def reset():
            d.enabled = False
            d.drive, d.mix = 1.0, 1.0
        self._reset_button(frame, row=3, col=1, reset_fn=reset)

    def _build_delay_tab(self, nb):
        frame = tk.Frame(nb, bg="#121212")
        nb.add(frame, text="Delay / Echo")
        self._cost_label(frame, "Delay")
        dl = self.track.effects.delay
        dl_var = self._check(frame, "Delay Enabled", lambda: dl.enabled, lambda v: setattr(dl, "enabled", v), row=0)
        self._slider(frame, "Time (sec)", 0.02, 2.0, lambda: dl.time_sec,
                     lambda v: setattr(dl, "time_sec", v), row=1, enable_var=dl_var, effect=dl)
        self._slider(frame, "Feedback", 0.0, 0.95, lambda: dl.feedback,
                     lambda v: setattr(dl, "feedback", v), row=2, enable_var=dl_var, effect=dl)
        self._slider(frame, "Mix", 0.0, 1.0, lambda: dl.mix, lambda v: setattr(dl, "mix", v),
                     row=3, enable_var=dl_var, effect=dl)

        def reset():
            dl.enabled = False
            dl.time_sec, dl.feedback, dl.mix = 0.35, 0.35, 0.25
        self._reset_button(frame, row=4, col=1, reset_fn=reset)

    def _build_reverb_tab(self, nb):
        frame = tk.Frame(nb, bg="#121212")
        nb.add(frame, text="Reverb")
        self._cost_label(frame, "Reverb")
        rv = self.track.effects.reverb
        rv_var = self._check(frame, "Reverb Enabled", lambda: rv.enabled, lambda v: setattr(rv, "enabled", v), row=0)
        self._slider(frame, "Room Size", 0.0, 1.0, lambda: rv.room_size, rv.set_room_size,
                     row=1, enable_var=rv_var, effect=rv)
        self._slider(frame, "Damping", 0.0, 1.0, lambda: rv.damping,
                     lambda v: setattr(rv, "damping", v), row=2, enable_var=rv_var, effect=rv)
        self._slider(frame, "Mix", 0.0, 1.0, lambda: rv.mix, lambda v: setattr(rv, "mix", v),
                     row=3, enable_var=rv_var, effect=rv)

        def reset():
            rv.enabled = False
            rv.set_room_size(0.6)
            rv.damping, rv.mix = 0.3, 0.25
        self._reset_button(frame, row=4, col=1, reset_fn=reset)


class _MasterBusProxy:
    """Minimal stand-in for a Track, so FxDialog's tab builders (which only
    ever touch `track.effects` and `track.name`) can drive the master bus
    chain unmodified."""

    def __init__(self, engine):
        self.effects = engine.master_fx_l
        self.name = "MASTER BUS"


class MasterFxDialog(FxDialog):
    """The master-bus effects rack. Edits engine.master_fx_l directly and
    mirrors every change into master_fx_r (see AudioEngine.sync_master_fx)
    so both stereo channels always share identical parameters while keeping
    independent filter/delay/reverb state."""

    def __init__(self, master, engine):
        self.engine = engine
        proxy = _MasterBusProxy(engine)
        super().__init__(master, proxy, key="__master__", title="MASTER BUS - FX Rack")

    def _after_param_change(self):
        self.engine.sync_master_fx()

    @classmethod
    def open_for_master(cls, master, engine):
        existing = cls._open_dialogs.get("__master__")
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing
        return cls(master, engine)
