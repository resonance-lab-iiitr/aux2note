"""
tools/gui_shot.py
Screenshots of the Tk GUI, for reviewing the layout without a real PC.

As a library:
    from tools.gui_shot import snap
    snap(root, "out.png")          # crops to the window when it can

From the command line (run from CODE/, under a virtual screen in the sandbox):
    xvfb-run -a -s "-screen 0 1366x768x24" python3 tools/gui_shot.py --tracks 3 --size 1366x768 --out shot.png

The launcher starts LiveLooperApp with the sounddevice stub (no sound card)
and adds N empty tracks. Needs ImageMagick (`import`) or Pillow ImageGrab.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _settle(root, rounds=4):
    for _ in range(rounds):
        root.update_idletasks()
        root.update()


def snap(root, path):
    """Save a PNG of the screen area covered by `root`. Returns the path."""
    _settle(root)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if shutil.which("import"):
        cmd = ["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", "+repage", path]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if res.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    try:
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
        return path
    except Exception as e:
        raise RuntimeError(f"no screenshot method worked (ImageMagick 'import' and PIL ImageGrab): {e}")


def _launch(tracks, width, height, out, scale):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from tests import _stubs  # noqa: F401  (sounddevice stub when no sound card library)
    import tkinter as tk
    from app import LiveLooperApp

    root = tk.Tk()
    app = LiveLooperApp(root)
    root.geometry(f"{width}x{height}+0+0")
    for _ in range(tracks):
        app.add_empty_track()
    if scale and scale != 1.0:
        try:
            import ui_theme
            ui_theme.set_scale(scale)
        except ImportError:
            pass
    root.update()
    path = snap(root, out)
    root.destroy()
    return path


def main():
    ap = argparse.ArgumentParser(description="Screenshot the Live Looper Pro window.")
    ap.add_argument("--tracks", type=int, default=0, help="empty tracks to add (default 0)")
    ap.add_argument("--size", default="1366x768", help="window size WxH (default 1366x768)")
    ap.add_argument("--scale", type=float, default=1.0, help="UI scale, needs ui_theme (default 1.0)")
    ap.add_argument("--out", default="shot.png", help="output PNG path")
    args = ap.parse_args()
    try:
        w, h = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        ap.error("--size must look like 1366x768")
    print(_launch(args.tracks, w, h, args.out, args.scale))


if __name__ == "__main__":
    main()
