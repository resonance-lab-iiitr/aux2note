"""
audio_engine.py
The real-time core: owns the sounddevice stream, the shared timeline playhead,
and mixes every independent Track together every callback. There is no single
"master loop" buffer - each track supplies its own samples for the current
playhead position, and the *engine* only optionally wraps the shared playhead
around a loop region if the user has switched the transport Loop checkbox on.
"""

import math
import threading
import time
import numpy as np
import sounddevice as sd

from dataclasses import replace

from effects import EffectsChain, InputCleanup, ParamSmoother, soft_limit
from stream_config import StreamConfig, build_ladder, check_same_hostapi
from settings_store import default_device_ids
from telemetry import Telemetry, short_mode
import latency_core
from split_stream import SplitStream
from debug_log import TestSignal


class AudioEngine:
    def __init__(self, sample_rate=48000, block_size=256, log=None):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._log = log or (lambda *a, **k: None)

        self.stream = None
        self.is_active = False
        self.active_config = None
        self.mode_name = "IDLE"

        # Phase 2: the audio callback NEVER takes a lock. It reads one
        # immutable tuple (_tracks_view). UI code builds a new tuple and swaps
        # the reference (a single atomic assignment in Python). `lock` only
        # serialises UI-side changes against each other (save, add, arm ...).
        self._tracks_view = ()
        self.lock = threading.RLock()

        # Latency compensation (samples). Phase 5 fills it from calibration;
        # Phase 4 adds a field to type it in.
        self.record_latency_samples = 0

        # Pre-allocated callback scratch arrays (re-made only if `frames` changes)
        self._scratch_frames = 0
        self._mix_l = self._mix_r = self._in_buf = None

        # Transport state
        self.playhead = 0
        self.is_playing = False
        self.loop_enabled = False      # the bottom "Loop" checkbox
        self.loop_start = 0
        self.loop_end = 0              # 0 means "use full arrangement length"

        self.master_gain = 1.0
        # rc10 clean-audio helpers (all touched only by the audio thread, except
        # the on/off flag, which the UI may flip at any time)
        self.input_cleanup_enabled = True
        self.input_cleanup = InputCleanup(sample_rate)
        self._master_smooth = ParamSmoother(sample_rate, 8.0)
        self._play_smooth = ParamSmoother(sample_rate, 8.0)
        self._flush_counter = 0
        self.master_fx_l = EffectsChain(sample_rate)
        self.master_fx_r = EffectsChain(sample_rate)
        self.master_fx_l.eq.enabled = True
        self.master_fx_r.eq.enabled = True

        # Loopback checkboxes:
        #  - input_monitor_enabled ("inline" loopback): always hear the raw
        #    live input through the output, even when nothing is armed.
        #  - record_with_output_enabled ("outline" loopback): while
        #    recording, blend the current master output back into what gets
        #    captured, so the new take includes everything already playing.
        self.input_monitor_enabled = False
        self.record_with_output_enabled = False
        self.monitor_gain = 1.0

        self.peak_l = 0.0
        self.peak_r = 0.0
        self.input_peak = 0.0

        # Phase 4a: plain-number counters, read by the GUI without a lock.
        self.telemetry = Telemetry()

        # Phase 5: calibration. `_calib` is set only while a measurement runs
        # (the callback then plays the chirp train instead of the looper mix).
        # `calibration` = {"rtt_ms", "rtt_samples", "key"} of the last good run.
        self._calib = None
        self.calibration = None

        # Phase 6: F12 test signal (None, or a TestSignal played INSTEAD of the mix)
        self._test = None
        self.test_signal_name = None
        self.debug_rt = None        # optional DebugLog: callback only counts events

        # Phase 10 (T020): raw capture tap. None, or a CaptureRecorder fed by
        # the callback wrapper. Set and cleared only from the UI thread.
        self.capture = None

    # ------------------------------------------------------------------ #
    # Device / stream lifecycle
    # ------------------------------------------------------------------ #
    def list_devices(self):
        devices = sd.query_devices()
        inputs, outputs = [], []
        for idx, dev in enumerate(devices):
            api_name = sd.query_hostapis(dev["hostapi"])["name"]
            label = f"ID {idx}: {dev['name']}  [{api_name}]"
            if dev["max_input_channels"] > 0:
                inputs.append((idx, label))
            if dev["max_output_channels"] > 0:
                outputs.append((idx, label))
        return inputs, outputs

    def probe_all_devices(self):
        """Full inventory of every audio driver/device the OS exposes, for
        the startup diagnostic log - not filtered to any one host API."""
        rows = []
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            default_in, default_out = default_device_ids(hostapis, sd.default.device)
        except Exception as e:
            return rows, str(e)

        for idx, dev in enumerate(devices):
            api_name = hostapis[dev["hostapi"]]["name"] if dev["hostapi"] < len(hostapis) else "?"
            rows.append({
                "id": idx,
                "name": dev["name"],
                "driver": api_name,
                "max_in": dev["max_input_channels"],
                "max_out": dev["max_output_channels"],
                "default_sr": dev.get("default_samplerate", 0.0),
                "is_default_in": idx in default_in,
                "is_default_out": idx in default_out,
            })
        return rows, None

    # ---- Stream opening (Phase 1: exclusive mode + fallback ladder) ---- #
    def _build_stream_kwargs(self, cfg):
        """The ONE place that decides the sounddevice.Stream arguments.
        Exclusive mode = WasapiSettings(exclusive=True) on input AND output,
        latency="low", float32, mono in / stereo out."""
        kwargs = dict(
            device=(cfg.in_device, cfg.out_device),
            samplerate=cfg.sample_rate,
            blocksize=cfg.block_size,
            channels=(cfg.channels_in, cfg.channels_out),
            dtype="float32",
            callback=self._callback,
        )
        if cfg.exclusive:
            kwargs["latency"] = cfg.latency
            kwargs["extra_settings"] = (sd.WasapiSettings(exclusive=True),
                                        sd.WasapiSettings(exclusive=True))
        return kwargs

    def _apply_sample_rate(self, rate):
        """Change the engine rate. Only legal when no tracks exist."""
        if rate == self.sample_rate:
            return
        self._log(f"[AUDIO] Engine sample rate {self.sample_rate} -> {rate} Hz", "SYS")
        old = self.master_fx_l.to_dict()
        self.sample_rate = rate
        self.master_fx_l = EffectsChain(rate)
        self.master_fx_r = EffectsChain(rate)
        self.master_fx_l.from_dict(old)
        self.master_fx_r.from_dict(old)

    def open_stream(self, in_device, out_device, cfg=None):
        """Open the audio stream, walking the fallback ladder.
        Raises RuntimeError (clear message) if every step fails.
        On success sets self.active_config and self.mode_name."""
        self.close_stream()
        if cfg is None:
            cfg = StreamConfig(sample_rate=self.sample_rate, block_size=self.block_size)
        cfg = replace(cfg, in_device=in_device, out_device=out_device)

        with self.lock:
            tracks_exist = len(self.tracks) > 0
        ladder = build_ladder(cfg, tracks_exist, self.sample_rate)
        if cfg.exclusive and tracks_exist:
            self._log("[AUDIO] Tracks exist, so the sample rate stays at "
                      f"{self.sample_rate} Hz (start a new project to change it).", "WARN")

        # Exclusive needs both devices on WASAPI: check once, up front.
        exclusive_blocked = None
        if cfg.exclusive:
            try:
                exclusive_blocked = check_same_hostapi(
                    cfg, sd.query_devices(), sd.query_hostapis())
            except Exception as e:
                exclusive_blocked = None  # let PortAudio decide
                self._log(f"[AUDIO] Host API check skipped ({e})", "WARN")

        orig_rate = self.sample_rate
        last_error = "no attempt was made"
        for step in ladder:
            label = step.short_label()
            if step.exclusive and exclusive_blocked:
                self._log(f"[AUDIO] Skipping {label}: {exclusive_blocked}", "WARN")
                last_error = exclusive_blocked
                continue

            self._log(f"[AUDIO] Trying {label} ...", "SYS")
            stream = None
            try:
                if step.sample_rate != self.sample_rate:
                    self._apply_sample_rate(step.sample_rate)
                if step.exclusive and step.split:
                    stream = SplitStream(step.in_device, step.out_device, step.sample_rate,
                                         step.block_size, step.channels_out, self._callback,
                                         latency=step.latency, exclusive=True)
                else:
                    stream = sd.Stream(**self._build_stream_kwargs(step))
                stream.start()
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                self._log(f"[AUDIO] Trying {label} ... FAILED ({last_error})", "WARN")
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                continue

            self.stream = stream
            self.sample_rate = step.sample_rate
            self.block_size = step.block_size
            self.active_config = step
            self.mode_name = step.mode_label()
            self.is_active = True
            self.telemetry.reset()
            self._log(f"[AUDIO] Trying {label} ... OK", "SUCCESS")
            self._log(f"[AUDIO] Running: {self.mode_name}", "SUCCESS")
            if not step.exclusive:
                self._log("[AUDIO] Shared mode: expect higher latency (about 37 ms round trip).", "WARN")
            # NOTE: mounting only starts the audio *stream* (I/O and
            # monitoring). It deliberately does NOT start the transport,
            # otherwise the first press of PLAY would stop it instead.
            self.is_playing = False
            return step

        if self.sample_rate != orig_rate:
            self._apply_sample_rate(orig_rate)
        self.active_config = None
        self.mode_name = "NONE"
        hint = ("Close other programs that use the sound card (browsers, Teams, "
                "music players), check that the selected input and output are the "
                "WASAPI devices, then try again.")
        raise RuntimeError(f"No audio mode could be opened. Last error: {last_error}. {hint}")

    def close_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            summ = getattr(self.stream, "summary", "")
            if summ:
                self._log("[AUDIO] " + summ + (" | trace: %s" % self.stream.trace_path
                          if getattr(self.stream, "trace_path", None) else ""), "SYS")
            self.stream = None
        self.is_active = False
        self._test = None
        self.test_signal_name = None
        self.is_playing = False
        self.mode_name = "IDLE"

    def split_stats(self):
        """SplitStream counters (dict) when the running stream is a split stream, else None."""
        f = getattr(self.stream, "stats", None)
        if f is None:
            return None
        try:
            return f()
        except Exception:
            return None

    def latency_ms(self):
        if self.stream is None:
            return 0.0
        try:
            return (self.stream.latency[0] + self.stream.latency[1]) * 1000.0
        except Exception:
            return 0.0

    # ---- Phase 5: measured latency ---- #
    def measured_rtt_ms(self):
        """Measured round trip (ms) if a calibration exists for the mode that
        is running now, else None."""
        c = self.calibration
        if c is not None and self.active_config is not None and c.get("key") == short_mode(self):
            return c["rtt_ms"]
        return None

    def set_calibration(self, rtt_ms, key=None):
        """Remember a result (also used to restore one from settings.json)
        and use it for record compensation."""
        key = key or short_mode(self)
        self.calibration = {"rtt_ms": float(rtt_ms), "key": key,
                            "rtt_samples": int(round(rtt_ms * self.sample_rate / 1000.0))}
        self.record_latency_samples = self.calibration["rtt_samples"]

    def run_calibration(self, level=latency_core.DEFAULT_LEVEL,
                        bursts=latency_core.DEFAULT_BURSTS):
        """Play a chirp train and record it back (cable Line Out -> Line In).
        BLOCKS for about 6 seconds: call it from a worker thread, never the
        Tk thread. Returns latency_core.summarize() dict. On status OK the
        result is stored via set_calibration()."""
        if not self.is_active or self.stream is None:
            raise RuntimeError("Mount the audio engine before calibrating.")
        if any(t.recording for t in self._tracks_view):
            raise RuntimeError("Stop recording before calibrating.")
        cal = latency_core.Calibrator(self.sample_rate, bursts, level)
        was_playing = self.is_playing
        self.is_playing = False
        self._log("[CALIB] Playing test chirps ...", "SYS")
        self._calib = cal                       # callback picks it up
        deadline = time.time() + cal.total / float(self.sample_rate) + 4.0
        try:
            while not cal.done and time.time() < deadline and self.is_active:
                time.sleep(0.02)
        finally:
            self._calib = None
            self.is_playing = was_playing
        if not cal.done:
            raise RuntimeError("Calibration did not finish (audio stream stalled).")
        res = cal.result()
        if res["status"] == latency_core.STATUS_OK:
            self.set_calibration(res["rtt_ms"])
            self._log(f"[CALIB] RTT {res['rtt_ms']:.2f} ms, jitter {res['jitter_ms']:.2f} ms, "
                      f"level {res['level_dbfs']:.1f} dBFS ({self.calibration['key']})", "SUCCESS")
        else:
            self._log(f"[CALIB] {res['status']}: {latency_core.ADVICE[res['status']]}", "WARN")
        return res

    def set_test_signal(self, kind, level=0.1):
        """kind 'sine' / 'noise' starts a test tone on the output (no cable
        needed); None stops it. Safe to call from the GUI thread."""
        if kind is None:
            self._test = None
            self.test_signal_name = None
            self._log("[TEST] Test signal off.", "SYS")
            return
        if kind not in ("sine", "noise"):
            raise ValueError("kind must be 'sine' or 'noise'")
        self._test = TestSignal(kind, self.sample_rate, level)
        self.test_signal_name = f"{kind} @ {self._test.level:.2f}"
        self._log(f"[TEST] Test signal {self.test_signal_name} on the output.", "SYS")

    # ---- Phase 10 (T020): raw capture tap (UI thread only) ------------- #
    def start_capture(self, max_seconds=120, capture_output=False,
                      channels_in=None, channels_out=None):
        """Start recording the exact sound card input plus per-block timing.
        All buffers are allocated here, off the audio thread. Returns the
        CaptureRecorder (also kept in `self.capture`)."""
        from capture_recorder import CaptureRecorder
        cfg = self.active_config
        if channels_in is None:
            channels_in = getattr(cfg, "channels_in", 1) if cfg is not None else 1
        if channels_out is None:
            channels_out = getattr(cfg, "channels_out", 2) if cfg is not None else 2
        rec = CaptureRecorder(self.sample_rate, self.block_size, channels_in,
                              channels_out, max_seconds=max_seconds,
                              capture_output=capture_output)
        self.capture = rec            # one atomic assignment: the callback sees it next block
        self._log(f"[CAPTURE] Raw capture started ({max_seconds} s max).", "SYS")
        return rec

    def stop_capture(self):
        """Detach and return the recorder (None if none was running). Its data
        stays valid; write it with recorder.to_files(folder)."""
        rec = self.capture
        self.capture = None
        if rec is not None:
            rec.stop()
            self._log(f"[CAPTURE] Raw capture stopped: {rec.seconds:.1f} s, "
                      f"{rec.n_blocks} blocks{' (buffer full)' if rec.full else ''}.", "SYS")
        return rec

    def cpu_load(self):
        """Our own measure: average callback time / block time (0..1+)."""
        return self.telemetry.cpu_load()

    def pa_cpu_load(self):
        """PortAudio's own CPU load figure (0..1), or None if unavailable."""
        try:
            return float(self.stream.cpu_load) if self.stream is not None else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Track management
    # ------------------------------------------------------------------ #
    @property
    def tracks(self):
        """A plain list COPY of the current tracks (safe to iterate anywhere).
        To change the set of tracks use add_track / remove_track, or assign
        a whole new list (`engine.tracks = [...]`), which swaps the snapshot."""
        return list(self._tracks_view)

    @tracks.setter
    def tracks(self, new_tracks):
        self._tracks_view = tuple(new_tracks)

    def add_track(self, track):
        with self.lock:
            self._tracks_view = self._tracks_view + (track,)
            self._recompute_loop_end()

    def remove_track(self, track):
        with self.lock:
            self._tracks_view = tuple(t for t in self._tracks_view if t is not track)
            self._recompute_loop_end()

    def clear_all_tracks(self):
        """Used by 'NEW PROJECT'. Atomically drops every track and resets
        the transport, so the realtime callback never sees a half-emptied
        track list."""
        with self.lock:
            self._tracks_view = ()
            self.playhead = 0
            self.loop_start = 0
            self.loop_end = 0
            self.is_playing = False

    def snapshot_tracks(self):
        """A stable, point-in-time copy of the track list for use by
        background threads (export, save) that must not race against the
        realtime callback adding/removing tracks mid-iteration."""
        return list(self._tracks_view)

    def arrangement_length(self):
        return max((t.end_offset for t in self._tracks_view), default=0)

    def _recompute_loop_end(self):
        if self.loop_end == 0 or self.loop_end < self.arrangement_length():
            self.loop_end = self.arrangement_length()

    # ------------------------------------------------------------------ #
    # Transport controls
    # ------------------------------------------------------------------ #
    def play(self):
        self.is_playing = True

    def stop(self):
        self.is_playing = False

    def rewind(self):
        with self.lock:
            self.playhead = self.loop_start

    def set_playhead_seconds(self, seconds):
        with self.lock:
            self.playhead = max(0, int(seconds * self.sample_rate))

    def sync_master_fx(self):
        """The master bus keeps two independent EffectsChain instances (one
        per channel) so their filter/delay/reverb state never crosses
        between L and R. The Master FX rack edits master_fx_l directly;
        call this after any parameter change so master_fx_r picks up the
        same settings (state stays independent, parameters stay identical)."""
        with self.lock:
            self.master_fx_r.from_dict(self.master_fx_l.to_dict())

    def set_loop_enabled(self, enabled):
        self.loop_enabled = enabled
        if enabled:
            self._recompute_loop_end()

    def arm_track(self, track, armed=True):
        """Arm (or unarm) a track. If another track was mid-recording when
        this is called, its take is properly committed via stop_recording()
        rather than silently discarded - arming a different track (or
        unarming one) while it was recording used to wipe the captured
        audio with no way to recover it."""
        with self.lock:
            if armed:
                for t in self._tracks_view:
                    if t is not track:
                        t.armed = False
                        if t.recording:
                            t.stop_recording()
            track.armed = armed
            if not armed and track.recording:
                track.stop_recording()
            self._recompute_loop_end()

    def start_recording_armed(self):
        """Arming + recording also makes sure the transport is rolling, so
        any already-recorded tracks play back while the new take is
        captured (classic overdub behaviour). Previously you could hit
        RECORD without ever pressing PLAY first: the take would still be
        captured, but the playhead never advanced, so it silently recorded
        in isolation with no way to hear or record over what was already on
        the timeline."""
        with self.lock:
            self.is_playing = True
            lat = max(0, int(self.record_latency_samples))
            pos = self.playhead
            started = False
            for t in self._tracks_view:
                if t.armed:
                    t.start_recording(pos, lat)
                    started = True
            if started and lat > 0:
                self._log("[LOOPER] Record offset compensated by "
                          f"{lat * 1000.0 / self.sample_rate:.1f} ms", "LOOPER")

    def stop_recording_armed(self):
        with self.lock:
            for t in self._tracks_view:
                if t.recording:
                    t.stop_recording()
            self._recompute_loop_end()

    def housekeeping(self):
        """Call from the UI thread every ~100 ms: lets long recordings grow
        their buffers off the audio thread."""
        for t in self._tracks_view:
            if t.recording:
                t.ensure_capacity()

    # ------------------------------------------------------------------ #
    # The real-time callback
    # ------------------------------------------------------------------ #
    def _ensure_scratch(self, frames):
        if frames != self._scratch_frames:
            self._mix_l = np.zeros(frames, dtype=np.float32)
            self._mix_r = np.zeros(frames, dtype=np.float32)
            self._in_buf = np.zeros(frames, dtype=np.float32)
            self._scratch_frames = frames

    def _callback(self, indata, outdata, frames, time_info, status):
        """Thin wrapper (T020): runs the real body, then hands the untouched
        input and the block timing to the capture tap when one is active. The
        body never modifies `indata`, so the tap sees the raw sound card data."""
        t_start = time.perf_counter()
        self._callback_body(indata, outdata, frames, time_info, status)
        cap = self.capture
        if cap is not None:
            cap.feed(indata, outdata, frames, time_info, status,
                     t_start, time.perf_counter())

    def _callback_body(self, indata, outdata, frames, time_info, status):
        t_start = time.perf_counter()
        cal = self._calib
        if cal is not None:          # calibration run: chirps only, no mix
            cal.process(indata, outdata, frames)
            self.telemetry.record(t_start, time.perf_counter(), frames,
                                  self.sample_rate, status)
            return
        ts = self._test
        if ts is not None:           # F12 test signal: tone/noise only, no mix
            pk = ts.process(outdata, frames)
            self.peak_l = self.peak_r = pk
            self.input_peak = float(np.max(np.abs(indata[:, 0]))) if indata.shape[1] > 0 and frames else 0.0
            self.telemetry.record(t_start, time.perf_counter(), frames,
                                  self.sample_rate, status)
            return
        self._ensure_scratch(frames)
        input_signal = self._in_buf
        if indata.shape[1] > 0:
            np.copyto(input_signal, indata[:, 0])
        else:
            input_signal.fill(0.0)
        self.input_peak = float(np.max(np.abs(input_signal))) if frames else 0.0
        if self.input_cleanup_enabled and frames:
            np.copyto(input_signal, self.input_cleanup.process(input_signal))

        mix_l = self._mix_l
        mix_r = self._mix_r
        mix_l.fill(0.0)
        mix_r.fill(0.0)

        # One atomic read of an immutable tuple. No lock in the audio thread.
        tracks = self._tracks_view
        pos = self.playhead
        any_solo = False
        for t in tracks:
            if t.solo:
                any_solo = True
                break
        armed_recording = [t for t in tracks if t.armed and t.recording]

        # Transport gate (rc10 fix): a STOPPED transport used to keep mixing the
        # same frozen block over and over (a buzz). Now playback fades out over
        # ~8 ms on STOP and fades in on PLAY; tracks are skipped while stopped.
        pg = self._play_smooth.step(1.0 if self.is_playing else 0.0, frames)
        stopped = _scalar_float(pg) and pg == 0.0

        # 1) Mix every already-existing, non-recording track first, so the
        #    "outline" loopback below can capture what's already playing.
        for t in tracks:
            if t in armed_recording:
                continue
            if stopped:
                t.peak = 0.0                         # T014: mixer meter reads this
                if t.tail_samples_left > 0:          # drop stale effect state
                    t.tail_samples_left = 0
                    t.effects.reset_state()
                continue
            samples = t.get_samples(pos, frames)
            if np.any(samples):
                # a signal is present: (re)arm the tail timer
                t.tail_samples_left = _tail_samples(t.effects, self.sample_rate)
                samples = t.effects.process(samples)
            elif t.tail_samples_left > 0:
                # silent input but delay/reverb is still ringing: keep
                # running the chain so the tail fades out naturally
                t.tail_samples_left -= frames
                samples = t.effects.process(samples)
                if t.tail_samples_left <= 0:
                    # tail is over: short fade on the last block, then forget
                    # all filter/delay memory so nothing stale clicks later
                    samples = samples * _fade_out(frames)
                    t.effects.reset_state()
            active = (not t.mute) and (not any_solo or t.solo)
            lg, rg = _track_gains(t, active, frames, self.sample_rate, pg)
            if _scalar_float(lg) and lg == 0.0 and _scalar_float(rg) and rg == 0.0:
                t.peak = 0.0
                continue
            t.peak = _abs_peak(samples) * t.gain   # T014: post-fader level, one float, no allocation
            mix_l += samples * lg
            mix_r += samples * rg

        # 2) "Outline" loopback: what's already playing gets folded into
        #    the material captured by any armed/recording track.
        existing_mono = (mix_l + mix_r) * 0.5 if self.record_with_output_enabled else None

        for t in armed_recording:
            capture = input_signal
            if existing_mono is not None:
                capture = np.clip(capture + existing_mono, -1.0, 1.0)
            t.feed_recording(capture)
            monitored = t.effects.process(capture.copy())
            active = (not t.mute) and (not any_solo or t.solo)
            lg, rg = _track_gains(t, active, frames, self.sample_rate, 1.0)
            if not (_scalar_float(lg) and lg == 0.0 and _scalar_float(rg) and rg == 0.0):
                t.peak = _abs_peak(monitored) * t.gain
                mix_l += monitored * lg
                mix_r += monitored * rg
            else:
                t.peak = 0.0

        # 3) "Inline" loopback: always let the raw live input through to
        #    the output, independent of arming/recording.
        if self.input_monitor_enabled:
            mono_in = input_signal * self.monitor_gain
            mix_l += mono_in
            mix_r += mono_in

        # Master bus: full FX chain, then a soft safety limiter.
        mg = self._master_smooth.step(self.master_gain, frames)
        out_l = soft_limit(self.master_fx_l.process(mix_l) * mg)
        out_r = soft_limit(self.master_fx_r.process(mix_r) * mg)
        self._flush_counter += 1
        if self._flush_counter >= 16:                # every ~40 ms, 1/8 of the sweep each time
            self._flush_counter = 0
            self.master_fx_l.flush_denormals()
            self.master_fx_r.flush_denormals()

        self.peak_l = float(np.max(np.abs(out_l))) if frames else 0.0
        self.peak_r = float(np.max(np.abs(out_r))) if frames else 0.0

        if self.is_playing:
            pos += frames
            if self.loop_enabled:
                region_len = max(1, self.loop_end - self.loop_start)
                pos = self.loop_start + ((pos - self.loop_start) % region_len)
            self.playhead = pos

        outdata[:, 0] = out_l
        if outdata.shape[1] > 1:
            outdata[:, 1] = out_r

        # Only counts numbers here; the GUI thread turns them into log lines.
        self.telemetry.record(t_start, time.perf_counter(), frames,
                              self.sample_rate, status)
        if status and self.debug_rt is not None:
            self.debug_rt.log_rt("PortAudio status flag")


def _tail_samples(chain, sample_rate):
    """How long (in samples) delay / reverb keep ringing after the input
    goes silent. Cheap arithmetic only, safe to call from the audio thread."""
    tail = int(0.25 * sample_rate)       # EQ / compressor / distortion ring-out
    d = chain.delay
    if d.enabled:
        fb = min(max(d.feedback, 0.0), 0.95)
        repeats = 1 if fb <= 0.0 else min(30, math.ceil(math.log(0.001) / math.log(fb)))
        tail = max(tail, int(d.time_sec * sample_rate * (repeats + 1)))
    r = chain.reverb
    if r.enabled:
        fb = 0.6 + r.room_size * 0.38
        repeats = min(200, math.ceil(math.log(0.001) / math.log(min(fb, 0.99))))
        tail = max(tail, int(repeats * 0.04 * sample_rate))   # longest comb ~40 ms
        tail = min(tail, int(8 * sample_rate))
    return tail


def _scalar_float(v):
    return isinstance(v, float)


def _abs_peak(x):
    """Largest absolute sample of a block as a float. max() and min() return scalars, so unlike
    np.abs(x).max() nothing is allocated (safe in the audio callback)."""
    if len(x) == 0:
        return 0.0
    hi = x.max()
    lo = x.min()
    return float(hi if hi > -lo else -lo)


_FADES = {}


def _fade_out(n):
    f = _FADES.get(n)
    if f is None:
        f = (1.0 - np.arange(1, n + 1, dtype=np.float32) / n)
        if len(_FADES) < 64:
            _FADES[n] = f
    return f


def _track_gains(t, active, frames, sample_rate, pg):
    """Smoothed (click-free) left/right gain for one track: volume, pan, mute,
    solo and the transport fade all glide over ~8 ms instead of stepping."""
    sm = getattr(t, "_gain_smooth", None)
    if sm is None:
        sm = t._gain_smooth = (ParamSmoother(sample_rate, 8.0), ParamSmoother(sample_rate, 8.0))
    lt, rt = _pan_gains(t.gain, t.pan)
    if not active:
        lt = rt = 0.0
    lg = sm[0].step(lt, frames)
    rg = sm[1].step(rt, frames)
    if not (_scalar_float(pg) and pg == 1.0):
        lg = lg * pg
        rg = rg * pg
    return lg, rg


def _pan_gains(gain, pan):
    pan = max(-1.0, min(1.0, pan))
    l_gain = gain * (1.0 - max(pan, 0.0))
    r_gain = gain * (1.0 + min(pan, 0.0))
    return l_gain, r_gain
