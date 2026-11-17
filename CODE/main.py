"""
main.py
Entry point - run this file to launch Live Looper Pro:

    python main.py
"""

import os
os.environ.setdefault("SD_ENABLE_ASIO", "1")

import tkinter as tk
from app import LiveLooperApp


def main():
    root = tk.Tk()
    app = LiveLooperApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
