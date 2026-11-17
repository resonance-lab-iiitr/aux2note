"""Phase 1: exclusive-mode stream opening and the fallback ladder.
No hardware: sounddevice is replaced by a fake module."""
import types
import unittest
from unittest import mock

from tests import _stubs  # noqa: F401
import audio_engine
from audio_engine import AudioEngine
from stream_config import StreamConfig, build_ladder, check_same_hostapi
from track import Track


class FakePortAudioError(Exception):
    pass


def make_fake_sd(fail_first=0, fail_always_exclusive=False, wasapi_devices=True,
                 fail_always=False, fail_rates_exclusive=()):
    """fail_first: number of Stream() constructions that raise before success."""
    state = {"attempts": [], "count": 0, "streams": []}
    api_idx = 0 if wasapi_devices else 1

    class WasapiSettings:
        def __init__(self, exclusive=False):
            self.exclusive = exclusive

    class Stream:
        def __init__(self, **kw):
            state["count"] += 1
            exclusive = "extra_settings" in kw
            state["attempts"].append((exclusive, kw["samplerate"], kw["blocksize"], kw))
            if fail_always:
                raise FakePortAudioError("Invalid sample rate [PaErrorCode -9997]")
            if state["count"] <= fail_first:
                raise FakePortAudioError("Invalid sample rate [PaErrorCode -9997]")
            if exclusive and fail_always_exclusive:
                raise FakePortAudioError("Device unavailable [PaErrorCode -9985]")
            if exclusive and kw["samplerate"] in fail_rates_exclusive:
                raise FakePortAudioError("Invalid sample rate [PaErrorCode -9997]")
            self.started = False
            self.closed = False
            state["streams"].append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.started = False

        def close(self):
            self.closed = True

    fake = types.SimpleNamespace(
        Stream=Stream, WasapiSettings=WasapiSettings, PortAudioError=FakePortAudioError,
        query_devices=lambda *a, **k: [{"hostapi": api_idx, "name": "Speakers"},
                                      {"hostapi": api_idx, "name": "Line In"}],
        query_hostapis=lambda *a, **k: [{"name": "Windows WASAPI"}, {"name": "MME"}],
    )
    return fake, state


def open_with(fake, engine=None, **cfg_kwargs):
    engine = engine or AudioEngine(sample_rate=48000, block_size=64)
    logs = []
    engine._log = lambda msg, level="INFO": logs.append((level, msg))
    with mock.patch.object(audio_engine, "sd", fake):
        return engine, logs, engine.open_stream(1, 0, StreamConfig(**cfg_kwargs)) \
            if cfg_kwargs else engine.open_stream(1, 0)


class TestLadderBuilder(unittest.TestCase):
    def test_order_without_tracks(self):
        steps = build_ladder(StreamConfig(), tracks_exist=False, current_rate=48000)
        self.assertEqual([(s.exclusive, s.sample_rate) for s in steps],
                         [(True, 48000), (True, 44100), (False, 48000)])

    def test_no_rate_change_when_tracks_exist(self):
        steps = build_ladder(StreamConfig(sample_rate=44100), tracks_exist=True, current_rate=44100)
        self.assertEqual([(s.exclusive, s.sample_rate) for s in steps],
                         [(True, 44100), (False, 44100)])

    def test_shared_only_has_one_step(self):
        steps = build_ladder(StreamConfig(exclusive=False), False, 48000)
        self.assertEqual(len(steps), 1)


class TestHostApiCheck(unittest.TestCase):
    def test_both_wasapi_ok(self):
        fake, _ = make_fake_sd()
        cfg = StreamConfig(in_device=1, out_device=0)
        self.assertIsNone(check_same_hostapi(cfg, fake.query_devices(), fake.query_hostapis()))

    def test_mme_rejected_with_reason(self):
        fake, _ = make_fake_sd(wasapi_devices=False)
        cfg = StreamConfig(in_device=1, out_device=0)
        why = check_same_hostapi(cfg, fake.query_devices(), fake.query_hostapis())
        self.assertIn("MME", why)


class TestOpenStream(unittest.TestCase):
    def test_first_try_exclusive_ok(self):
        fake, st = make_fake_sd()
        eng, logs, step = open_with(fake)
        self.assertTrue(eng.is_active)
        self.assertEqual(eng.mode_name, "WASAPI EXCLUSIVE 48000 Hz / 64")
        self.assertEqual(len(st["attempts"]), 1)
        kw = st["attempts"][0][3]
        self.assertEqual(kw["latency"], "low")
        self.assertEqual(kw["channels"], (1, 2))
        self.assertTrue(all(s.exclusive for s in kw["extra_settings"]))
        self.assertTrue(any("Trying exclusive 48000/64 ... OK" in m for _, m in logs))
        self.assertFalse(eng.is_playing)

    def test_falls_back_to_other_rate(self):
        fake, st = make_fake_sd(fail_first=1)
        eng, logs, _ = open_with(fake)
        self.assertEqual(eng.mode_name, "WASAPI EXCLUSIVE 44100 Hz / 64")
        self.assertEqual(eng.sample_rate, 44100)
        self.assertTrue(any("FAILED" in m for _, m in logs))

    def test_falls_back_to_shared(self):
        fake, st = make_fake_sd(fail_always_exclusive=True)
        eng, logs, _ = open_with(fake)
        self.assertEqual(eng.mode_name, "SHARED 48000 Hz / 64")
        self.assertEqual([a[0] for a in st["attempts"]], [True, True, False])
        self.assertNotIn("extra_settings", st["attempts"][-1][3])
        self.assertEqual(eng.sample_rate, 48000)

    def test_all_fail_raises_clear_error(self):
        fake, st = make_fake_sd(fail_always=True)
        eng = AudioEngine(sample_rate=48000, block_size=64)
        eng._log = lambda *a, **k: None
        with mock.patch.object(audio_engine, "sd", fake):
            with self.assertRaises(RuntimeError) as cm:
                eng.open_stream(1, 0)
        self.assertIn("No audio mode could be opened", str(cm.exception))
        self.assertFalse(eng.is_active)
        self.assertEqual(eng.mode_name, "NONE")
        self.assertEqual(eng.sample_rate, 48000)  # restored

    def test_non_wasapi_devices_skip_exclusive(self):
        fake, st = make_fake_sd(wasapi_devices=False)
        eng, logs, _ = open_with(fake)
        self.assertEqual(eng.mode_name, "SHARED 48000 Hz / 64")
        self.assertEqual(len(st["attempts"]), 1)
        self.assertTrue(any("Skipping exclusive" in m for _, m in logs))

    def test_rate_is_kept_when_tracks_exist(self):
        fake, st = make_fake_sd(fail_always_exclusive=True)
        eng = AudioEngine(sample_rate=44100, block_size=64)
        eng.add_track(Track("t1", 44100))
        eng, logs, _ = open_with(fake, engine=eng, sample_rate=44100)
        self.assertEqual(eng.sample_rate, 44100)
        self.assertEqual(eng.mode_name, "SHARED 44100 Hz / 64")

    def test_close_stream_resets_mode(self):
        fake, st = make_fake_sd()
        eng, _, _ = open_with(fake)
        with mock.patch.object(audio_engine, "sd", fake):
            eng.close_stream()
        self.assertEqual(eng.mode_name, "IDLE")
        self.assertFalse(eng.is_active)

    def test_old_constructor_args_still_work(self):
        eng = AudioEngine(sample_rate=48000, block_size=256)
        self.assertEqual((eng.sample_rate, eng.block_size), (48000, 256))


if __name__ == "__main__":
    unittest.main()
