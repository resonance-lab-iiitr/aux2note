# T009: timeline view model (CODE/timeline_view.py)

Pure Python, no Tk. Not used by the app yet (T011 swaps it in for `waveform_widget.TimelineView`).

- `TimelineView(px_per_sec=80, height_level=2)`: same `sec_to_px`, `px_to_sec`, `zoom(factor)`, `add_listener` as before.
- Zoom limits 4 to 2000 px per second (the old limit was 10 to 2000).
- `zoom_at(factor, mouse_x, scroll_px)` for Ctrl+wheel: returns the new scroll offset so the time under the mouse stays put.
- `fit(total_seconds, viewport_px)` for a FIT button (returns scroll 0, leaves 5 % free on the right).
- `height_up()` / `height_down()`: row heights 48, 72, 96 (default, the old row), 140, 200 px.
- `visible_range(scroll_px, viewport_px)`, `ticks(viewport_px, scroll_px)` -> `Tick(sec, x, label, major)`, labels like `1:15`, `0:00.25`; ticks at least 60 px apart at every zoom.
- `to_dict()` / `TimelineView.from_dict(d)` to save the zoom in settings later (bad data falls back to defaults).
