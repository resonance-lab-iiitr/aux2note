"""
ui_theme.py
Shared look for every window: colour palette, named (scalable) fonts, ttk
styles and a UI scale factor.

Usage (after the Tk root exists):

    import ui_theme as theme
    theme.apply_theme(root)              # safe to call more than once
    tk.Label(root, text="Hi", font=theme.font("UI_BOLD"), bg=theme.PALETTE["surface1"])
    theme.set_scale(1.25)                # every named font and Treeview row grows
    theme.add_scale_listener(callback)   # callback(new_scale) for widgets that
                                         # size things in pixels (use theme.scaled(px))

Never hard-code font tuples in new code: use font("NAME") so the scale works.
"""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- palette
PALETTE = {
    "bg": "#121212",         # window background (surface level 0)
    "surface1": "#1E1E1E",   # panels
    "surface2": "#2D2D2D",   # inputs, raised controls
    "surface3": "#333333",   # neutral buttons, borders
    "border": "#333333",
    "text": "#E0E0E0",
    "muted": "#8A8A8A",
    "accent": "#00FF66",
    "accent_active": "#00CC52",
    "warn": "#FFCC00",
    "error": "#FF5555",
    "record": "#FF3333",
    "record_active": "#CC0000",
    "fx": "#B266FF",
    "fx_active": "#9A4DFF",
    "hint_bg": "#0D2B17",
    "hint_fg": "#8CFFB0",
}

# ------------------------------------------------------------------ fonts
SCALE_MIN, SCALE_MAX = 0.8, 2.0

# key -> (tk named font, preferred families, base size in points, extra options)
_FONT_SPECS = {
    "UI": ("LL_UI", ("Segoe UI", "Helvetica", "DejaVu Sans", "Arial"), 10, {}),
    "UI_BOLD": ("LL_UI_BOLD", ("Segoe UI", "Helvetica", "DejaVu Sans", "Arial"), 10, {"weight": "bold"}),
    "MONO": ("LL_MONO", ("Consolas", "DejaVu Sans Mono", "Courier New", "Courier"), 10, {}),
    "TITLE": ("LL_TITLE", ("Segoe UI", "Helvetica", "DejaVu Sans", "Arial"), 14, {"weight": "bold"}),
    "SMALL": ("LL_SMALL", ("Segoe UI", "Helvetica", "DejaVu Sans", "Arial"), 9, {}),
}
FONT_NAMES = {key: spec[0] for key, spec in _FONT_SPECS.items()}

_BASE_ROW_HEIGHT = 24      # Treeview row height in px at scale 1.0
_scale = 1.0
_root = None
_listeners = []


def font(key):
    """Name of the shared tk font for `key` (UI, UI_BOLD, MONO, TITLE, SMALL).
    Pass the result to any widget's `font=` option."""
    return FONT_NAMES[key]


def get_scale():
    return _scale


def scaled(px):
    """Pixel size multiplied by the current UI scale (int, at least 1)."""
    return max(1, int(round(px * _scale)))


def add_scale_listener(callback):
    if callback not in _listeners:
        _listeners.append(callback)


def remove_scale_listener(callback):
    if callback in _listeners:
        _listeners.remove(callback)


def _pick_family(root, candidates):
    try:
        available = {f.lower(): f for f in tkfont.families(root)}
    except tk.TclError:
        available = {}
    for name in candidates:
        if name.lower() in available:
            return available[name.lower()]
    return candidates[-1]


def _font_size(base):
    return max(6, int(round(base * _scale)))


_font_objs = {}      # key -> (root, tkfont.Font). Tk deletes a named font when its Font object is
                     # garbage-collected, so these references must stay alive.


def _ensure_fonts(root):
    for key, (name, families, base, extra) in _FONT_SPECS.items():
        family = _pick_family(root, families)
        held = _font_objs.get(key)
        if held is not None and held[0] is root:
            held[1].configure(family=family, size=_font_size(base), **extra)
            continue
        _font_objs[key] = (root, tkfont.Font(root=root, name=name, family=family,
                                             size=_font_size(base), **extra))


# ----------------------------------------------------------------- styles
def _configure_styles(root):
    p = PALETTE
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    ui, ui_b, mono, small = font("UI"), font("UI_BOLD"), font("MONO"), font("SMALL")
    pad_btn = (scaled(12), scaled(5))

    style.configure(".", background=p["bg"], foreground=p["text"], font=ui)
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabel", background=p["bg"], foreground=p["text"], font=ui)
    style.configure("TCheckbutton", background=p["bg"], foreground=p["text"], font=ui)
    style.map("TCheckbutton", background=[("active", p["bg"])])
    style.configure("TLabelframe", background=p["surface1"], bordercolor=p["border"], borderwidth=1)
    style.configure("TLabelframe.Label", background=p["surface1"], foreground=p["accent"], font=mono)

    # Buttons
    for name, bg, fg, active, fnt in (
            ("Action", p["accent"], p["bg"], p["accent_active"], ui_b),
            ("Stop", p["record"], "#FFFFFF", p["record_active"], ui_b),
            ("Fx", p["fx"], p["bg"], p["fx_active"], ui_b),
            ("Neutral", p["surface3"], p["text"], "#444444", ui)):
        style.configure(f"{name}.TButton", background=bg, foreground=fg, font=fnt,
                        borderwidth=0, padding=pad_btn)
        style.map(f"{name}.TButton", background=[("active", active)])

    # Combobox
    style.configure("TCombobox", fieldbackground=p["surface2"], background=p["surface3"],
                    foreground=p["text"], arrowcolor=p["text"], font=ui)
    style.map("TCombobox", fieldbackground=[("readonly", p["surface2"])],
              foreground=[("readonly", p["text"])])
    root.option_add("*TCombobox*Listbox.font", ui)
    root.option_add("*TCombobox*Listbox.background", p["surface2"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])

    # Scale (slider)
    style.configure("TScale", background=p["bg"], troughcolor=p["surface2"])
    style.configure("Horizontal.TScale", background=p["bg"], troughcolor=p["surface2"])
    style.configure("Vertical.TScale", background=p["bg"], troughcolor=p["surface2"])

    # Slim dark scrollbars
    sb_w = scaled(10)
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=p["surface3"], troughcolor=p["bg"],
                        bordercolor=p["bg"], lightcolor=p["surface3"], darkcolor=p["surface3"],
                        arrowcolor=p["muted"], gripcount=0, arrowsize=sb_w, width=sb_w)
        style.map(f"{orient}.TScrollbar", background=[("active", "#555555")])

    # Treeview
    style.configure("Treeview", background=p["surface1"], fieldbackground=p["surface1"],
                    foreground=p["text"], rowheight=scaled(_BASE_ROW_HEIGHT), font=ui,
                    bordercolor=p["border"])
    style.configure("Treeview.Heading", background=p["surface3"], foreground=p["text"], font=ui_b)
    style.map("Treeview", background=[("selected", "#245C3A")], foreground=[("selected", "#FFFFFF")])

    # Notebook with large tab headers
    style.configure("TNotebook", background=p["bg"], borderwidth=0, tabmargins=(scaled(4), scaled(4), 0, 0))
    style.configure("TNotebook.Tab", background=p["surface3"], foreground=p["muted"], font=ui_b,
                    padding=(scaled(20), scaled(9)), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", p["surface1"]), ("active", "#444444")],
              foreground=[("selected", p["accent"]), ("active", p["text"])])

    # Small helper label style
    style.configure("Muted.TLabel", foreground=p["muted"], font=small)


def apply_theme(root):
    """Create the named fonts and configure every ttk style. Idempotent."""
    global _root
    _root = root
    root.configure(bg=PALETTE["bg"])
    _ensure_fonts(root)
    _configure_styles(root)


def set_scale(value):
    """Set the UI scale (clamped to 0.8-2.0). Resizes the named fonts and
    ttk metrics, then calls every listener. Returns the scale actually used."""
    global _scale, _root
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 1.0
    _scale = max(SCALE_MIN, min(SCALE_MAX, value))
    if _root is not None:
        try:
            _ensure_fonts(_root)
            _configure_styles(_root)
        except tk.TclError:
            _root = None      # window was destroyed; next apply_theme() picks up the new scale
    for cb in list(_listeners):
        try:
            cb(_scale)
        except Exception:
            pass   # one broken listener must not stop the others
    return _scale
