"""
timeline_view.py
Pure-Python model of the shared timeline: horizontal zoom (pixels per second),
fit-to-window, vertical track-height levels and readable ruler ticks.
No Tk import, so it is fully unit-testable. Drop-in for the old
waveform_widget.TimelineView (same sec_to_px, px_to_sec, zoom, add_listener).

    view = TimelineView()
    scroll = view.zoom_at(1.25, mouse_x, scroll)   # Ctrl+wheel: zoom around the cursor
    scroll = view.fit(total_seconds, viewport_px)  # FIT button
    view.height_up() / view.height_down()          # vertical zoom (row height in px)
    for tick in view.ticks(viewport_px, scroll):   # ruler marks
        draw(tick.x, tick.label, tick.major)
    saved = view.to_dict(); view = TimelineView.from_dict(saved)

Listeners (no arguments) are called after every change.
"""
import math
from collections import namedtuple

MIN_PX_PER_SEC = 4.0
MAX_PX_PER_SEC = 2000.0
DEFAULT_PX_PER_SEC = 80.0
HEIGHT_LEVELS = (48, 72, 96, 140, 200)   # track row height in px
DEFAULT_HEIGHT_LEVEL = 2                  # 96 px = the old fixed row height
MIN_TICK_SPACING_PX = 60

# Step sizes in seconds that read well on a ruler: 1, 2, 5, 10, 15, 30 s, 1, 2, 5, 10 min ...
NICE_STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30,
              60, 120, 300, 600, 900, 1800, 3600, 7200)

Tick = namedtuple("Tick", "sec x label major")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ruler_step(px_per_sec, min_spacing_px=MIN_TICK_SPACING_PX):
    """Smallest nice step (seconds) whose ticks are at least min_spacing_px apart."""
    px_per_sec = max(1e-9, float(px_per_sec))
    for step in NICE_STEPS:
        if step * px_per_sec >= min_spacing_px:
            return step
    return NICE_STEPS[-1]


def format_time(sec, step):
    """Label for a tick: M:SS, H:MM:SS, or M:SS.d / M:SS.dd when the step is under a second."""
    decimals = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    sec = max(0.0, float(sec))
    # Work in integer hundredths to avoid float artefacts such as 0:00.30000000004.
    units = int(round(sec * (10 ** decimals)))
    whole, frac = divmod(units, 10 ** decimals)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    text = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    if decimals:
        text += f".{frac:0{decimals}d}"
    return text


def ruler_ticks(px_per_sec, viewport_px, scroll_px=0.0, min_spacing_px=MIN_TICK_SPACING_PX):
    """Labelled ticks covering the visible part of the timeline (plus one step either side).
    Returns a list of Tick(sec, x, label, major); x is the absolute timeline pixel.
    Ticks are at least min_spacing_px apart; every 5th tick of a step is major."""
    px_per_sec = _clamp(float(px_per_sec), MIN_PX_PER_SEC, MAX_PX_PER_SEC)
    step = ruler_step(px_per_sec, min_spacing_px)
    start_sec = max(0.0, scroll_px / px_per_sec)
    end_sec = (scroll_px + max(0.0, viewport_px)) / px_per_sec
    first = max(0, int(math.floor(start_sec / step)) - 1)
    last = int(math.ceil(end_sec / step)) + 1
    out = []
    for i in range(first, last + 1):
        sec = i * step
        out.append(Tick(sec, sec * px_per_sec, format_time(sec, step), i % 5 == 0))
    return out


class TimelineView:
    MIN_PX_PER_SEC = MIN_PX_PER_SEC
    MAX_PX_PER_SEC = MAX_PX_PER_SEC
    HEIGHT_LEVELS = HEIGHT_LEVELS

    def __init__(self, px_per_sec=DEFAULT_PX_PER_SEC, height_level=DEFAULT_HEIGHT_LEVEL):
        self.px_per_sec = _clamp(float(px_per_sec), MIN_PX_PER_SEC, MAX_PX_PER_SEC)
        self.height_level = int(_clamp(int(height_level), 0, len(HEIGHT_LEVELS) - 1))
        self.listeners = []

    # ----------------------------------------------------------- listeners
    def add_listener(self, fn):
        if fn not in self.listeners:
            self.listeners.append(fn)

    def remove_listener(self, fn):
        if fn in self.listeners:
            self.listeners.remove(fn)

    def _notify(self):
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:
                pass   # one broken listener must not stop the others

    # ------------------------------------------------------- horizontal scale
    def sec_to_px(self, sec):
        return sec * self.px_per_sec

    def px_to_sec(self, px):
        return px / self.px_per_sec

    def set_px_per_sec(self, value):
        new = _clamp(float(value), MIN_PX_PER_SEC, MAX_PX_PER_SEC)
        if new != self.px_per_sec:
            self.px_per_sec = new
            self._notify()
        return self.px_per_sec

    def zoom(self, factor):
        """Zoom about the timeline start (old behaviour, used by the ZOOM +/- buttons)."""
        return self.set_px_per_sec(self.px_per_sec * factor)

    def zoom_at(self, factor, anchor_x, scroll_px=0.0):
        """Zoom so the time under `anchor_x` (viewport pixel, e.g. the mouse) stays
        at the same screen x. Returns the new scroll offset in pixels (never negative)."""
        anchor_sec = (scroll_px + anchor_x) / self.px_per_sec
        self.set_px_per_sec(self.px_per_sec * factor)
        return max(0.0, anchor_sec * self.px_per_sec - anchor_x)

    def fit(self, total_seconds, viewport_px, margin_frac=0.05):
        """Zoom so `total_seconds` fills the viewport, leaving margin_frac of it free on
        the right. Returns the new scroll offset (0.0). An empty arrangement keeps the zoom."""
        if total_seconds and total_seconds > 0 and viewport_px and viewport_px > 0:
            usable = viewport_px * (1.0 - _clamp(margin_frac, 0.0, 0.5))
            self.set_px_per_sec(usable / total_seconds)
        return 0.0

    def visible_range(self, scroll_px, viewport_px):
        """(start_sec, end_sec) shown in the viewport."""
        start = max(0.0, scroll_px / self.px_per_sec)
        return start, start + max(0.0, viewport_px) / self.px_per_sec

    def ticks(self, viewport_px, scroll_px=0.0):
        return ruler_ticks(self.px_per_sec, viewport_px, scroll_px)

    # ------------------------------------------------------- vertical scale
    @property
    def track_height(self):
        return HEIGHT_LEVELS[self.height_level]

    def set_height_level(self, level):
        level = int(_clamp(int(level), 0, len(HEIGHT_LEVELS) - 1))
        if level != self.height_level:
            self.height_level = level
            self._notify()
        return self.track_height

    def height_up(self):
        return self.set_height_level(self.height_level + 1)

    def height_down(self):
        return self.set_height_level(self.height_level - 1)

    # ------------------------------------------------------------ persistence
    def to_dict(self):
        return {"px_per_sec": self.px_per_sec, "height_level": self.height_level}

    @classmethod
    def from_dict(cls, data):
        """Rebuild from to_dict() output; missing or invalid values fall back to defaults."""
        data = data if isinstance(data, dict) else {}
        try:
            pps = float(data.get("px_per_sec", DEFAULT_PX_PER_SEC))
            if not math.isfinite(pps):
                pps = DEFAULT_PX_PER_SEC
        except (TypeError, ValueError):
            pps = DEFAULT_PX_PER_SEC
        try:
            level = int(data.get("height_level", DEFAULT_HEIGHT_LEVEL))
        except (TypeError, ValueError):
            level = DEFAULT_HEIGHT_LEVEL
        return cls(pps, level)
