"""
audio_settings_panel.py  (Live Looper Pro v2.0, Phase 4b)

Panel [1]: driver, Exclusive/Shared, sample rate, block size, input/output
devices (filtered by driver), record offset (ms), AUTO button, MOUNT button.
All decisions live in settings_store.py; this file only wires widgets.
"""

import tkinter as tk
from tkinter import ttk

import settings_store as ss


class AudioSettingsPanel(ttk.LabelFrame):
    def __init__(self, master, on_mount, on_change=None, log=None, on_calibrate=None):
        super().__init__(master, text=" AUDIO DEVICES & CALIBRATION ", padding=12)
        self._on_change = on_change or (lambda: None)
        self._log = log or (lambda *a, **k: None)
        self._all_in, self._all_out, self._rows = [], [], []
        self._shown_in, self._shown_out = [], []
        self._busy = False   # True while we set widgets ourselves
        self.calibration = None   # {"rtt_ms", "key"} of the last good calibration

        self.driver_var = tk.StringVar(value=ss.DEFAULT_SETTINGS["driver"])
        self.exclusive_var = tk.BooleanVar(value=True)
        self.split_var = tk.BooleanVar(value=ss.DEFAULT_SETTINGS["split"])
        self.rate_var = tk.StringVar(value="48000")
        self.block_var = tk.StringVar(value=str(ss.DEFAULT_SETTINGS["block_size"]))
        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.offset_var = tk.StringVar(value="0")

        self.columnconfigure(0, weight=1)
        # Section 1: devices and stream settings. Section 2: calibration (T012).
        self.devices_frame = ttk.Frame(self)
        self.devices_frame.grid(row=0, column=0, sticky="ew")
        self.calib_frame = ttk.Frame(self)
        self.calib_frame.grid(row=2, column=0, sticky="ew")
        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=10)
        d, c = self.devices_frame, self.calib_frame
        for col in (0, 1, 2, 3, 4):
            d.columnconfigure(col, weight=1)

        ttk.Label(d, text="DEVICES", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))
        ttk.Label(d, text="Driver:").grid(row=1, column=0, sticky="w")
        ttk.Label(d, text="Mode:").grid(row=1, column=1, sticky="w")
        ttk.Label(d, text="Sample rate:").grid(row=1, column=2, sticky="w")
        ttk.Label(d, text="Block size:").grid(row=1, column=3, sticky="w")

        self.driver_combo = ttk.Combobox(d, textvariable=self.driver_var, state="readonly")
        self.driver_combo.grid(row=2, column=0, sticky="ew", padx=(0, 6))

        mode = ttk.Frame(d)
        mode.grid(row=2, column=1, sticky="w")
        self.excl_radio = ttk.Radiobutton(mode, text="Exclusive", value=True,
                                          variable=self.exclusive_var, command=self._changed)
        self.excl_radio.pack(side="left", padx=(0, 8))
        self.shared_radio = ttk.Radiobutton(mode, text="Shared", value=False,
                                            variable=self.exclusive_var, command=self._changed)
        self.shared_radio.pack(side="left", padx=(0, 8))
        self.split_check = ttk.Checkbutton(mode, text="Split in/out", variable=self.split_var,
                                           command=self._changed)
        self.split_check.pack(side="left")

        self.rate_combo = ttk.Combobox(d, textvariable=self.rate_var, state="readonly",
                                       values=[str(r) for r in (44100, 48000)], width=8)
        self.rate_combo.grid(row=2, column=2, sticky="ew", padx=6)
        self.block_combo = ttk.Combobox(d, textvariable=self.block_var, state="readonly",
                                        values=[str(b) for b in ss.BLOCK_SIZES], width=6)
        self.block_combo.grid(row=2, column=3, sticky="ew", padx=6)

        self.auto_btn = ttk.Button(d, text="AUTO (recommended)", style="Neutral.TButton",
                                   command=self.apply_auto)
        self.auto_btn.grid(row=2, column=4, sticky="ew", padx=(6, 0))

        ttk.Label(d, text="Input Device:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(d, text="Output Device:").grid(row=3, column=2, columnspan=3, sticky="w", pady=(8, 0))
        self.in_combo = ttk.Combobox(d, textvariable=self.in_var, state="readonly")
        self.in_combo.grid(row=4, column=0, columnspan=2, sticky="ew", padx=(0, 6))
        self.out_combo = ttk.Combobox(d, textvariable=self.out_var, state="readonly")
        self.out_combo.grid(row=4, column=2, columnspan=3, sticky="ew", padx=(6, 0))

        self.mount_btn = ttk.Button(d, text="MOUNT AUDIO ENGINE", style="Action.TButton",
                                    command=on_mount)
        self.mount_btn.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(10, 0))

        c.columnconfigure(1, weight=1)
        ttk.Label(c, text="CALIBRATION", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.calib_btn = ttk.Button(c, text="CALIBRATE LATENCY", style="Neutral.TButton",
                                    state="disabled", command=on_calibrate or (lambda: None))
        self.calib_btn.grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.calib_lbl = ttk.Label(c, text="not calibrated (latency shown is only what the driver reports)",
                                   wraplength=520, justify="left")
        self.calib_lbl.grid(row=1, column=1, sticky="w")
        off = ttk.Frame(c)
        off.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(off, text="Record offset (ms):").pack(side="left")
        self.offset_entry = ttk.Entry(off, textvariable=self.offset_var, width=7)
        self.offset_entry.pack(side="left", padx=6)
        ttk.Label(off, text="(shifts new takes earlier to cancel round-trip delay; 0 = off)",
                  style="Muted.TLabel").pack(side="left")
        self.offset_entry.bind("<FocusOut>", lambda e: self._offset_changed())
        self.offset_entry.bind("<Return>", lambda e: self._offset_changed())

        self.driver_combo.bind("<<ComboboxSelected>>", lambda e: self._driver_changed())
        for cb in (self.rate_combo, self.block_combo, self.in_combo, self.out_combo):
            cb.bind("<<ComboboxSelected>>", lambda e: self._changed())

    # ---------------- devices ---------------- #
    def set_devices(self, inputs, outputs, rows, saved=None):
        """Fill the lists from the engine scan, then preselect `saved`
        (a settings dict) or the Windows defaults."""
        self._all_in, self._all_out, self._rows = list(inputs), list(outputs), list(rows)
        drivers = ss.driver_names(self._all_in + self._all_out)
        self.driver_combo["values"] = drivers
        saved = saved or ss.DEFAULT_SETTINGS
        self._busy = True
        try:
            if saved["driver"] in drivers:
                self.driver_var.set(saved["driver"])
            elif drivers:
                self.driver_var.set(ss.WASAPI_NAME if ss.WASAPI_NAME in drivers else drivers[0])
            self.exclusive_var.set(saved["exclusive"])
            self.split_var.set(bool(saved.get("split", ss.DEFAULT_SETTINGS["split"])))
            self.rate_var.set(str(saved["sample_rate"]))
            self.block_var.set(str(saved["block_size"]))
            self.offset_var.set(f"{saved['record_offset_ms']:g}")
            self.set_calibration(saved.get("calibration"))
            self._fill_devices(saved.get("in_device", ""), saved.get("out_device", ""))
            self._update_mode_state()
        finally:
            self._busy = False

    def _fill_devices(self, in_name="", out_name=""):
        drv = self.driver_var.get()
        self._shown_in = ss.filter_by_driver(self._all_in, drv)
        self._shown_out = ss.filter_by_driver(self._all_out, drv)
        self.in_combo["values"] = [l for _, l in self._shown_in]
        self.out_combo["values"] = [l for _, l in self._shown_out]
        for combo, var, shown, name, key in (
                (self.in_combo, self.in_var, self._shown_in, in_name, "is_default_in"),
                (self.out_combo, self.out_var, self._shown_out, out_name, "is_default_out")):
            var.set("")
            if not shown:
                continue
            i = ss.index_by_name(shown, name)
            if i is None:
                i = ss.preferred_index(shown, self._rows, key)
            combo.current(i)

    def _update_mode_state(self):
        wasapi = ss.is_wasapi(self.driver_var.get())
        if not wasapi:
            self.exclusive_var.set(False)
        state = "normal" if wasapi else "disabled"
        self.excl_radio.config(state=state)

    # ---------------- events ---------------- #
    def _driver_changed(self):
        if self._busy:
            return
        self._busy = True
        try:
            self._fill_devices()
            self._update_mode_state()
        finally:
            self._busy = False
        self._changed()

    def _changed(self):
        if not self._busy:
            self._on_change()

    def _offset_changed(self):
        v = ss.parse_offset_ms(self.offset_var.get())
        if v is None:
            self._log("Record offset must be a number from 0 to "
                      f"{ss.MAX_OFFSET_MS:g} ms; value reset to 0.", "WARN")
            self.offset_var.set("0")
        self._changed()

    def apply_auto(self):
        a = ss.auto_choice()
        if a["driver"] not in self.driver_combo["values"]:
            self._log("AUTO: no WASAPI driver found on this PC; keeping current settings.", "WARN")
            return
        self._busy = True
        try:
            self.driver_var.set(a["driver"])
            self.exclusive_var.set(True)
            self.split_var.set(bool(a.get("split", True)))
            self.rate_var.set(str(a["sample_rate"]))
            self.block_var.set(str(a["block_size"]))
            self._fill_devices()          # Windows default devices
            self._update_mode_state()
        finally:
            self._busy = False
        self._log("AUTO: WASAPI exclusive (split in/out) %d Hz / block %d, default devices."
                  % (a["sample_rate"], a["block_size"]), "SYS")
        self._changed()

    def apply_settings(self, s):
        """Set the widgets from a settings dict (used to revert a change)."""
        self.set_devices(self._all_in, self._all_out, self._rows, saved=s)

    def set_rate_block(self, rate=None, block=None):
        """Show a project's rate / block in the widgets (no remount prompt)."""
        self._busy = True
        try:
            if rate in (44100, 48000):
                self.rate_var.set(str(rate))
            if block in ss.BLOCK_SIZES:
                self.block_var.set(str(block))
        finally:
            self._busy = False

    def set_rate_locked(self, locked):
        self.rate_combo.config(state="disabled" if locked else "readonly")

    def set_mounted(self, mounted):
        self.mount_btn.config(text="UNMOUNT AUDIO ENGINE" if mounted else "MOUNT AUDIO ENGINE",
                              style="Stop.TButton" if mounted else "Action.TButton")
        self.calib_btn.config(state="normal" if mounted else "disabled")

    def set_calibration(self, cal):
        """cal = {"rtt_ms", "key"} or None. Updates the label; the record
        offset box is set separately with set_offset_ms()."""
        self.calibration = dict(cal) if cal else None
        self.calib_lbl.config(text=(f"calibrated: {cal['rtt_ms']:.1f} ms for {cal['key']}"
                                    if cal else "not calibrated (latency shown is only what the driver reports)"))

    def set_offset_ms(self, ms):
        self.offset_var.set(f"{ms:.1f}")

    # ---------------- values ---------------- #
    def record_offset_ms(self):
        v = ss.parse_offset_ms(self.offset_var.get())
        return 0.0 if v is None else v

    def device_ids(self):
        """(in_id, out_id) or (None, None) if nothing is selected."""
        try:
            return (ss.parse_device_id(self.in_var.get()),
                    ss.parse_device_id(self.out_var.get()))
        except Exception:
            return None, None

    def get_config(self):
        i, o = self.device_ids()
        return ss.build_config(self.driver_var.get(), self.exclusive_var.get(),
                               self.rate_var.get(), self.block_var.get(), i, o,
                               split=self.split_var.get())

    def get_settings(self):
        cfg = self.get_config()
        return dict(driver=cfg.api, exclusive=cfg.exclusive, split=cfg.split, sample_rate=cfg.sample_rate,
                    block_size=cfg.block_size, record_offset_ms=self.record_offset_ms(),
                    in_device=ss.name_of(self.in_var.get()) if self.in_var.get() else "",
                    out_device=ss.name_of(self.out_var.get()) if self.out_var.get() else "",
                    calibration=self.calibration)
