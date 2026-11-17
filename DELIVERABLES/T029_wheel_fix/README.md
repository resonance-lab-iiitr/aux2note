# T029: mouse-wheel error fixed
Error from the real PC (2026-11-12 14:40:26): `'str' object has no attribute 'winfo_containing'` in `scroll_frame.py`. Cause: Tk gives `event.widget` as a plain string for widgets without a Python object (for example a drop-down list); the handler called a method on it. Fix: `_pointer_widget` falls back to the Tk root for the pointer lookup and ignores a str widget. See `scroll_frame.diff`.
Test: `test_wheel_event_with_string_widget_does_not_raise` in `CODE/tests/test_phase9_ui_foundation.py` (failed before with the same traceback, passes after). Full suite: 520 tests OK (python3.12 under xvfb).
Real-PC check still needed: run the app, open a combobox list and scroll the wheel over it; the log must show no CRIT line.
