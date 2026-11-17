"""
tab_mixer.py  (Phase 9 / T014)
The Mixer tab: one channel strip per track, a master strip, and a compact inline FX rack.

Replaces tabs.MixerTab through tabs.load_tab("mixer", ...). app.py and tabs.py are not edited.

Channel strip (top to bottom): track name, ARM / M / S toggles, PAN slider, vertical volume
fader with a level meter, volume readout, five FX on/off toggles (EQ CMP DST DLY REV) and an
"FX..." button that opens the existing FxDialog. The master strip has the same layout with the
master fader (engine.master_gain, kept in step with the top-bar slider), L/R meters and a
MASTER FX button.

Where the numbers come from:
  * per-track level: `track.peak`, one float the audio callback sets for every track on each
    block (post-fader, 0.0 when silent, muted, or stopped). Tracks that never ran have no such
    attribute yet, so the tab reads it with getattr(..., 0.0).
  * master level: engine.peak_l / engine.peak_r.
The tab shows meters only while the engine stream is active (engine.is_active), so a stale
value left over from a closed stream is never drawn.

Track state changes made here go through the same calls as the Tracks tab strips
(engine.arm_track, app._on_track_changed) so both tabs stay equal; on_show() re-syncs the whole
tab from the model and adds / removes strips when the track list changed.
"""
import math
import tkinter as tk
from tkinter import ttk

import ui_theme as theme
from scroll_frame import ScrollableFrame
from tabs import BaseTab
from fx_dialog import FxDialog

FX_SLOTS = (("EQ", "eq"), ("CMP", "compressor"), ("DST", "distortion"),
            ("DLY", "delay"), ("REV", "reverb"))

STRIP_WIDTH = 104          # px at scale 1.0
MASTER_WIDTH = 132
FADER_LENGTH = 176
METER_WIDTH = 12
METER_FLOOR_DB = -60.0
METER_DECAY = 0.82         # displayed level falls to 82 % per 150 ms tick when the signal drops
CLIP_LEVEL = 0.99

_ARM_ON = "#FF3333"
_MUTE_ON = "#FFAA00"
_SOLO_ON = "#FFEE33"


def level_to_fraction(level):
    """Meter height 0..1 for a linear level (dB scale from -60 dB to 0 dB, clipped at 1)."""
    if level <= 0.0:
        return 0.0
    db = 20.0 * math.log10(level)
    if db <= METER_FLOOR_DB:
        return 0.0
    return min(1.0, (db - METER_FLOOR_DB) / -METER_FLOOR_DB)


def format_gain(gain):
    """'-6.0 dB' style readout for a linear gain; '-inf' at zero."""
    if gain <= 0.0005:
        return "-inf dB"
    return f"{20.0 * math.log10(gain):+.1f} dB"


def format_pan(pan):
    if abs(pan) < 0.02:
        return "C"
    return f"{abs(pan):.2f}{'L' if pan < 0 else 'R'}"


def _toggle(parent, text, var, color, command, width=3):
    """A small push-to-toggle button (Checkbutton without indicator)."""
    p = theme.PALETTE
    return tk.Checkbutton(parent, text=text, variable=var, command=command, indicatoron=False,
                          width=width, bg=p["surface3"], fg=p["text"], selectcolor=color,
                          activebackground="#444444", activeforeground=p["text"],
                          font=theme.font("SMALL"), relief="flat", bd=0, highlightthickness=0,
                          padx=2, pady=3, takefocus=False)


class _Meter:
    """Vertical level bar on a tk.Canvas. Fixed pixel size; the Mixer tab rebuilds strips on a scale change."""

    def __init__(self, parent, height, channels=1):
        self.channels = channels
        self.width = theme.scaled(METER_WIDTH) * channels + theme.scaled(2) * (channels - 1)
        self.height = height
        self.canvas = tk.Canvas(parent, width=self.width, height=height, bg="#0A0A0A",
                                highlightthickness=0, bd=0)
        self.shown = [0.0] * channels        # displayed linear levels (with fall-off)

    def update(self, levels):
        self.canvas.delete("all")
        cw = theme.scaled(METER_WIDTH)
        gap = theme.scaled(2)
        for i, level in enumerate(levels):
            shown = max(level, self.shown[i] * METER_DECAY)
            self.shown[i] = shown if shown > 1e-4 else 0.0
            frac = level_to_fraction(self.shown[i])
            x0 = i * (cw + gap)
            if frac > 0:
                top = self.height - int(frac * self.height)
                color = "#FF3333" if self.shown[i] >= CLIP_LEVEL else (
                    "#FFCC00" if frac > 0.85 else "#00FF66")
                self.canvas.create_rectangle(x0, top, x0 + cw, self.height, fill=color, width=0)

    def reset(self):
        self.shown = [0.0] * self.channels
        self.canvas.delete("all")


class _FxRack:
    """Five on/off toggles bound to an EffectsChain's `enabled` flags plus a button that opens
    the full rack. `get_chains()` returns the chains to switch (one for a track, L and R for
    the master bus); `after_change()` runs after a toggle (the master bus mirrors L into R)."""

    def __init__(self, parent, get_chains, open_full, open_text="FX...", after_change=None):
        self.get_chains = get_chains
        self.after_change = after_change
        self.vars = {}
        self.buttons = {}
        box = tk.Frame(parent, bg=theme.PALETTE["surface1"])
        self.frame = box
        for label, attr in FX_SLOTS:
            var = tk.BooleanVar(value=False)
            btn = _toggle(box, label, var, theme.PALETTE["fx"], lambda a=attr: self._on_toggle(a),
                          width=6)
            btn.pack(fill="x", pady=1)
            self.vars[attr] = var
            self.buttons[attr] = btn
        ttk.Button(box, text=open_text, style="Fx.TButton", takefocus=False,
                   command=open_full).pack(fill="x", pady=(3, 0))
        self.sync()

    def _on_toggle(self, attr):
        on = self.vars[attr].get()
        for chain in self.get_chains():
            getattr(chain, attr).enabled = on
        if self.after_change:
            self.after_change()

    def sync(self):
        chains = self.get_chains()
        for _label, attr in FX_SLOTS:
            self.vars[attr].set(bool(getattr(chains[0], attr).enabled))


class ChannelStrip(tk.Frame):
    """One track's strip. All widget state is re-read from the Track by sync()."""

    def __init__(self, parent, tab, track):
        p = theme.PALETTE
        super().__init__(parent, bg=p["surface1"], width=theme.scaled(STRIP_WIDTH),
                         highlightbackground=p["border"], highlightthickness=1)
        self.tab = tab
        self.track = track
        self.arm_var = tk.BooleanVar(value=track.armed)
        self.mute_var = tk.BooleanVar(value=track.mute)
        self.solo_var = tk.BooleanVar(value=track.solo)

        self.name_lbl = tk.Label(self, text=track.name, bg=p["surface1"], fg=track.color,
                                 font=theme.font("UI_BOLD"), anchor="center")
        self.name_lbl.pack(fill="x", padx=4, pady=(6, 4))

        row = tk.Frame(self, bg=p["surface1"])
        row.pack(padx=4, pady=2)
        self.arm_btn = _toggle(row, "ARM", self.arm_var, _ARM_ON, self._on_arm)
        self.mute_btn = _toggle(row, "M", self.mute_var, _MUTE_ON, self._on_mute, width=2)
        self.solo_btn = _toggle(row, "S", self.solo_var, _SOLO_ON, self._on_solo, width=2)
        self.solo_btn.configure(fg=p["text"])
        for b in (self.arm_btn, self.mute_btn, self.solo_btn):
            b.pack(side="left", padx=1)

        tk.Label(self, text="PAN", bg=p["surface1"], fg=p["muted"], font=theme.font("SMALL")).pack(
            pady=(6, 0))
        self.pan_scale = tk.Scale(self, from_=-1.0, to=1.0, resolution=0.01, orient="horizontal",
                                  showvalue=False, length=theme.scaled(STRIP_WIDTH - 24),
                                  bg=p["surface1"], troughcolor=p["surface2"], fg=p["text"],
                                  highlightthickness=0, bd=0, sliderlength=theme.scaled(16),
                                  command=self._on_pan)
        self.pan_scale.pack(padx=4)
        self.pan_scale.bind("<Double-Button-1>", lambda e: (self.pan_scale.set(0.0), "break")[1])
        self.pan_lbl = tk.Label(self, text="C", bg=p["surface1"], fg="#00CFFF",
                                font=theme.font("SMALL"))
        self.pan_lbl.pack()

        mid = tk.Frame(self, bg=p["surface1"])
        mid.pack(pady=(6, 0))
        self.vol_scale = tk.Scale(mid, from_=2.0, to=0.0, resolution=0.01, orient="vertical",
                                  showvalue=False, length=theme.scaled(FADER_LENGTH),
                                  bg=p["surface1"], troughcolor=p["surface2"], fg=p["text"],
                                  highlightthickness=0, bd=0, sliderlength=theme.scaled(22),
                                  width=theme.scaled(18), command=self._on_vol)
        self.vol_scale.pack(side="left", padx=(0, 6))
        self.vol_scale.bind("<Double-Button-1>", lambda e: (self.vol_scale.set(1.0), "break")[1])
        self.meter = _Meter(mid, theme.scaled(FADER_LENGTH))
        self.meter.canvas.pack(side="left")
        self.vol_lbl = tk.Label(self, text="0.0 dB", bg=p["surface1"], fg=p["accent"],
                                font=theme.font("SMALL"))
        self.vol_lbl.pack(pady=(2, 6))

        self.rack = _FxRack(self, lambda: [self.track.effects],
                            lambda: tab.app.open_fx(self.track))
        self.rack.frame.pack(fill="x", padx=6, pady=(0, 8))
        self.sync()

    # ---- model -> widgets (no commands fire for Checkbutton var.set; Scale.set may call
    # its command, which only writes the same value back) ------------------------------- #
    def sync(self):
        t = self.track
        self.name_lbl.configure(text=t.name, fg=t.color)
        self.arm_var.set(t.armed)
        self.mute_var.set(t.mute)
        self.solo_var.set(t.solo)
        self.vol_scale.set(t.gain)
        self.pan_scale.set(t.pan)
        self.vol_lbl.configure(text=format_gain(t.gain))
        self.pan_lbl.configure(text=format_pan(t.pan))
        self.rack.sync()

    # ---- widgets -> model -------------------------------------------------------------- #
    def _on_arm(self):
        self.tab.app.engine.arm_track(self.track, self.arm_var.get())
        self.tab.app._on_track_changed()       # Tracks tab strips re-sync (arming unarms others)
        self.tab.sync_states()

    def _on_mute(self):
        self.track.mute = self.mute_var.get()
        self.tab.app._on_track_changed()

    def _on_solo(self):
        self.track.solo = self.solo_var.get()
        self.tab.app._on_track_changed()

    def _on_vol(self, val):
        self.track.gain = float(val)
        self.vol_lbl.configure(text=format_gain(self.track.gain))
        self.tab.sync_tracks_tab_strip(self.track)

    def _on_pan(self, val):
        self.track.pan = float(val)
        self.pan_lbl.configure(text=format_pan(self.track.pan))
        self.tab.sync_tracks_tab_strip(self.track)

    # ---- meter ------------------------------------------------------------------------- #
    def update_meter(self, live):
        self.meter.update([float(getattr(self.track, "peak", 0.0)) if live else 0.0])


class MasterStrip(tk.Frame):
    def __init__(self, parent, tab):
        p = theme.PALETTE
        super().__init__(parent, bg=p["surface1"], width=theme.scaled(MASTER_WIDTH),
                         highlightbackground=p["accent"], highlightthickness=1)
        self.tab = tab
        engine = tab.app.engine
        tk.Label(self, text="MASTER", bg=p["surface1"], fg=p["accent"],
                 font=theme.font("UI_BOLD")).pack(padx=4, pady=(6, 4))
        # same height as a channel strip's ARM/M/S + PAN rows so the faders line up
        tk.Frame(self, bg=p["surface1"], height=theme.scaled(84)).pack()
        mid = tk.Frame(self, bg=p["surface1"])
        mid.pack(pady=(6, 0))
        self.vol_scale = tk.Scale(mid, from_=2.0, to=0.0, resolution=0.01, orient="vertical",
                                  showvalue=False, length=theme.scaled(FADER_LENGTH),
                                  bg=p["surface1"], troughcolor=p["surface2"], fg=p["text"],
                                  highlightthickness=0, bd=0, sliderlength=theme.scaled(22),
                                  width=theme.scaled(18), command=self._on_vol)
        self.vol_scale.pack(side="left", padx=(0, 6))
        self.vol_scale.bind("<Double-Button-1>", lambda e: (self.vol_scale.set(1.0), "break")[1])
        self.meter = _Meter(mid, theme.scaled(FADER_LENGTH), channels=2)
        self.meter.canvas.pack(side="left")
        self.vol_lbl = tk.Label(self, text="0.0 dB", bg=p["surface1"], fg=p["accent"],
                                font=theme.font("SMALL"))
        self.vol_lbl.pack(pady=(2, 6))
        self.rack = _FxRack(self, lambda: [engine.master_fx_l, engine.master_fx_r],
                            tab.app.open_master_fx, open_text="MASTER FX...")
        self.rack.frame.pack(fill="x", padx=6, pady=(0, 8))
        self.sync()

    def sync(self):
        gain = self.tab.app.engine.master_gain
        self.vol_scale.set(gain)
        self.vol_lbl.configure(text=format_gain(gain))
        # the master chains are normally identical; show the L chain
        self.rack.sync()

    def _on_vol(self, val):
        engine = self.tab.app.engine
        engine.master_gain = float(val)
        self.vol_lbl.configure(text=format_gain(engine.master_gain))
        top = getattr(self.tab.app, "master_vol", None)     # keep the top-bar slider in step
        if top is not None and abs(float(top.get()) - engine.master_gain) > 1e-6:
            top.set(engine.master_gain)

    def update_meter(self, live):
        e = self.tab.app.engine
        self.meter.update([float(e.peak_l), float(e.peak_r)] if live else [0.0, 0.0])


class Tab(BaseTab):
    title = "Mixer"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        p = theme.PALETTE
        self.engine = app.engine
        self.strips = {}                    # track.id -> ChannelStrip
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.scroll = ScrollableFrame(self, vertical=True, horizontal=True)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        self.body = self.scroll.body
        self.empty_lbl = tk.Label(
            self.body, bg=p["bg"], fg="#555555", font=theme.font("UI"),
            text="No tracks yet - click '+ TRACK' or 'IMPORT' to add one.\n"
                 "Each track gets a channel strip here.")
        self.master_strip = MasterStrip(self, self)
        self.master_strip.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=8)
        self._rebuild_tracks()
        theme.add_scale_listener(self._on_scale)

    # ---- UI scale (T016) -------------------------------------------------------------- #
    def _on_scale(self, scale):
        """Strip sizes (fader, meter, widths) are fixed at build time, so build every strip again.
        Nothing is lost: each strip re-reads gain, pan, arm / mute / solo and the FX toggles from
        the Track / engine in sync()."""
        try:
            for strip in list(self.strips.values()):
                strip.destroy()
            self.strips.clear()
            self.master_strip.destroy()
            self.master_strip = MasterStrip(self, self)
            self.master_strip.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=8)
            self._rebuild_tracks()
            self.sync_states()
        except tk.TclError:
            pass

    def destroy(self):
        theme.remove_scale_listener(self._on_scale)
        super().destroy()

    # ---- track list -> strips --------------------------------------------------------- #
    def _rebuild_tracks(self):
        """Make the strip set equal to engine.tracks (add new, drop removed, keep order)."""
        tracks = list(self.engine.tracks)
        ids = {t.id for t in tracks}
        for tid in [i for i in self.strips if i not in ids]:
            self.strips.pop(tid).destroy()
        for t in tracks:
            if t.id not in self.strips:
                self.strips[t.id] = ChannelStrip(self.body, self, t)
        for strip in self.strips.values():
            strip.pack_forget()
        self.empty_lbl.pack_forget()
        for t in tracks:
            self.strips[t.id].pack(side="left", fill="y", padx=3, pady=0)
        if not tracks:
            self.empty_lbl.pack(padx=40, pady=60)

    def sync_states(self):
        for strip in self.strips.values():
            strip.sync()
        self.master_strip.sync()

    def sync_tracks_tab_strip(self, track):
        """Light update of the matching Tracks tab header (volume / pan sliders, readouts);
        a full refresh_track_ui_states() would also redraw every waveform on each slider step."""
        tracks_tab = getattr(self.app, "tracks_tab", None)
        strip = getattr(tracks_tab, "track_strips", {}).get(track.id) if tracks_tab else None
        if strip is not None:
            strip.sync_from_model()

    # ---- tab contract ----------------------------------------------------------------- #
    def on_show(self):
        self._rebuild_tracks()
        self.sync_states()
        self.on_tick()

    def on_tick(self):
        live = bool(getattr(self.engine, "is_active", False))
        for strip in self.strips.values():
            strip.update_meter(live)
        self.master_strip.update_meter(live)
