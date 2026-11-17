"""
tab_debug.py  (Phase 9 / T013)
The Debug tab: a full-size Debug Center (log with level chips and search, engine cards,
sortable Devices / Tracks tables, LOAD history, report preview).

Replaces tabs.DebugTab through tabs.load_tab("debug", ...). The Debug Center is built by
app.create_debug_center(parent), which also sets app.debug_center and app.console.
"""
from tabs import BaseTab


class Tab(BaseTab):
    title = "Debug"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.center = app.create_debug_center(self)
        self.center.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

    def on_show(self):
        self.center.refresh()

    def on_tick(self):
        self.center.tick()
