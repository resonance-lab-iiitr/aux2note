"""Windows power plan check.

Measured on the development PC: with the Balanced plan the CPU slows down between
audio blocks and the live soak failed (hundreds of late blocks); with High performance
the same test passed. So the app warns when the Balanced or Power saver plan is active.

Only reads the plan (powercfg /getactivescheme). It never changes it.
"""
import re
import subprocess
import sys

BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
POWER_SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"
HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"

_SLOW_PLANS = {BALANCED: "Balanced", POWER_SAVER: "Power saver"}

_LINE = re.compile(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\s*(?:\(([^)]*)\))?")


def parse_active_scheme(text):
    """Parse the output of 'powercfg /getactivescheme'.
    Returns (guid_lowercase, name) or None if no GUID is found."""
    m = _LINE.search(text or "")
    if not m:
        return None
    return m.group(1).lower(), (m.group(2) or "").strip()


def get_active_scheme():
    """(guid, name) of the active Windows power plan, or None (not Windows / failed)."""
    if not sys.platform.startswith("win"):
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True,
                             text=True, timeout=3, creationflags=flags)
        return parse_active_scheme(out.stdout)
    except Exception:
        return None


def warning_for(scheme):
    """A warning text when the plan is known to cause dropouts, else None.
    Unknown or custom plans give no warning (they may be fine)."""
    if not scheme:
        return None
    guid, name = scheme
    if guid in _SLOW_PLANS:
        return (f"[AUDIO] Windows power plan is '{_SLOW_PLANS[guid]}'. The CPU can slow down between "
                "audio blocks and cause crackles. For best results choose High performance: "
                "Control Panel > Power Options > High performance (see README).")
    return None


def describe(scheme):
    """One line for the debug report."""
    if not scheme:
        return "n/a (not Windows or could not be read)"
    guid, name = scheme
    return f"{name or 'unnamed'} ({guid})"
