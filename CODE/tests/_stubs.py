"""
Makes the project importable on machines with no sound card library
(CI, sandboxes). If the real `sounddevice` imports fine it is left alone.
Import this module BEFORE importing audio_engine.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import sounddevice  # noqa: F401
except Exception:  # PortAudio missing, or not installed
    sd = types.ModuleType("sounddevice")

    class PortAudioError(Exception):
        pass

    class Stream:  # never actually opened in tests
        def __init__(self, *a, **k):
            raise PortAudioError("sounddevice stub: no audio hardware in tests")

    sd.Stream = Stream
    sd.PortAudioError = PortAudioError
    sd.query_devices = lambda *a, **k: []
    sd.query_hostapis = lambda *a, **k: []
    sd.default = types.SimpleNamespace(device=(None, None))
    sys.modules["sounddevice"] = sd
