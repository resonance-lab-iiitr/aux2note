"""
track.py
A single, fully independent audio track/strip.

There is no forced "master loop" here: every track owns its own audio clip,
its own position (offset) on the shared timeline, and its own loop on/off
switch. You can freely drag a track along the timeline to line it up with
any other track, exactly like clips in a normal audio editor.
"""

import uuid
import numpy as np

from effects import EffectsChain

TRACK_COLORS = ["#00FF66", "#00CFFF", "#FF9900", "#FF3388", "#B266FF", "#FFEE33", "#33FFDD"]


class Track:
    _color_cycle = 0
    REC_INITIAL_SECONDS = 300      # 5 minutes allocated when recording starts

    def __init__(self, name, sample_rate):
        self.id = uuid.uuid4().hex[:8]
        self.name = name
        self.sample_rate = sample_rate

        self.buffer = np.zeros(0, dtype=np.float32)   # this track's own clip audio
        self.offset = 0                                # start position on the shared timeline (samples)

        self.loop_enabled = False   # per-track "loop this clip" checkbox
        self.gain = 1.0             # linear volume/intensity, 0..2
        self.pan = 0.0              # -1 (L) .. +1 (R)
        self.mute = False
        self.solo = False
        self.armed = False          # armed to receive the next recording
        self.recording = False

        self.color = TRACK_COLORS[Track._color_cycle % len(TRACK_COLORS)]
        Track._color_cycle += 1

        self.effects = EffectsChain(sample_rate)

        self._rec_buf = np.zeros(0, dtype=np.float32)   # pre-allocated take buffer
        self._rec_pos = 0
        self._rec_skip = 0          # head samples to drop (latency compensation before time 0)
        self.tail_samples_left = 0  # delay/reverb tail still ringing (audio thread)
        self.peaks_cache = None     # (num_px, min, max) cache for waveform drawing
        self.peak = 0.0             # post-fader level of the last block; the engine writes it (T014, T028)

    # ------------------------------------------------------------------ #
    # Basic properties
    # ------------------------------------------------------------------ #
    @property
    def length(self):
        return len(self.buffer)

    @property
    def end_offset(self):
        return self.offset + self.length

    def duration_sec(self):
        return self.length / float(self.sample_rate)

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #
    def start_recording(self, at_sample, latency_samples=0):
        """Begin a brand new recording for this track.

        at_sample is the playhead position when RECORD was pressed.
        latency_samples is the measured round-trip delay: the sound that
        arrives at the input now was played that long ago, so the take is
        anchored EARLIER on the timeline (offset = at_sample - latency).
        If that would be before time 0, the head of the take is trimmed
        instead (see feed_recording).

        The whole recording buffer is allocated HERE (UI thread), so the
        audio callback never allocates or concatenates."""
        latency_samples = max(0, int(latency_samples))
        offset = int(at_sample) - latency_samples
        self._rec_skip = 0
        if offset < 0:
            self._rec_skip = -offset
            offset = 0
        self.buffer = np.zeros(0, dtype=np.float32)
        self.offset = offset
        self._rec_buf = np.zeros(int(self.sample_rate * self.REC_INITIAL_SECONDS), dtype=np.float32)
        self._rec_pos = 0
        self.peaks_cache = None
        self.recording = True      # set last: the callback may see it at once

    def feed_recording(self, block):
        """Called from the audio thread. Copies into the pre-allocated
        buffer; no allocation unless the buffer is completely full (the UI
        normally enlarges it earlier through ensure_capacity)."""
        if self._rec_skip:
            k = min(self._rec_skip, len(block))
            self._rec_skip -= k
            block = block[k:]
        n = len(block)
        if n == 0:
            return
        buf = self._rec_buf
        pos = self._rec_pos
        end = pos + n
        if end > len(buf):                       # last-resort emergency growth
            self._grow(max(end, len(buf) * 2))
            buf = self._rec_buf
        buf[pos:end] = block
        self._rec_pos = end

    def _grow(self, new_len):
        old = self._rec_buf
        new = np.zeros(int(new_len), dtype=np.float32)
        pos0 = self._rec_pos
        new[:pos0] = old[:pos0]
        self._rec_buf = new
        # the audio thread may have written a block into `old` meanwhile
        pos1 = self._rec_pos
        if pos1 > pos0:
            new[pos0:pos1] = old[pos0:pos1]

    def ensure_capacity(self, seconds_ahead=60.0):
        """UI-thread housekeeping: keep at least `seconds_ahead` of free
        space by doubling the buffer, so the audio thread never has to."""
        if not self.recording:
            return False
        free = len(self._rec_buf) - self._rec_pos
        if free < self.sample_rate * seconds_ahead:
            self._grow(len(self._rec_buf) * 2)
            return True
        return False

    def stop_recording(self):
        """Commit the take: trim the pre-allocated buffer, no concatenate."""
        self.recording = False
        pos = self._rec_pos
        if pos > 0:
            if pos * 2 >= len(self._rec_buf):
                self.buffer = self._rec_buf[:pos]          # cheap view
            else:
                self.buffer = self._rec_buf[:pos].copy()   # release the big block
        self._rec_buf = np.zeros(0, dtype=np.float32)
        self._rec_pos = 0
        self.peaks_cache = None

    # ------------------------------------------------------------------ #
    # Import
    # ------------------------------------------------------------------ #
    def import_audio(self, filepath, at_sample=0):
        import soundfile as sf

        data, sr = sf.read(filepath, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if sr != self.sample_rate:
            data = _resample_linear(data, sr, self.sample_rate)
        self.buffer = data.astype(np.float32)
        self.offset = at_sample
        self.peaks_cache = None

    def load_from_array(self, array, offset):
        self.buffer = np.asarray(array, dtype=np.float32)
        self.offset = offset
        self.peaks_cache = None

    # ------------------------------------------------------------------ #
    # Playback: gather `count` samples of this track's contribution
    # starting at absolute timeline sample `timeline_pos`.
    # ------------------------------------------------------------------ #
    def get_samples(self, timeline_pos, count):
        if self.length == 0:
            return np.zeros(count, dtype=np.float32)

        if self.loop_enabled:
            rel_start = (timeline_pos - self.offset) % self.length
            idx = (rel_start + np.arange(count)) % self.length
            return self.buffer[idx]

        start = timeline_pos - self.offset
        end = start + count
        out = np.zeros(count, dtype=np.float32)
        src_start = max(start, 0)
        src_end = min(end, self.length)
        if src_start < src_end:
            dst_start = src_start - start
            dst_end = dst_start + (src_end - src_start)
            out[dst_start:dst_end] = self.buffer[src_start:src_end]
        return out

    # ------------------------------------------------------------------ #
    # Waveform peaks for drawing (min/max per pixel column)
    # ------------------------------------------------------------------ #
    def compute_peaks(self, num_px):
        if self.length == 0 or num_px <= 0:
            return np.zeros(0), np.zeros(0)
        if self.peaks_cache is not None and self.peaks_cache[0] == num_px:
            return self.peaks_cache[1], self.peaks_cache[2]

        chunk = max(1, self.length // num_px)
        trimmed = self.buffer[: chunk * (self.length // chunk)] if chunk > 1 else self.buffer
        if len(trimmed) == 0:
            trimmed = self.buffer
        try:
            reshaped = trimmed[: chunk * (len(trimmed) // chunk)].reshape(-1, chunk)
            mins = reshaped.min(axis=1)
            maxs = reshaped.max(axis=1)
        except ValueError:
            mins = np.array([self.buffer.min()])
            maxs = np.array([self.buffer.max()])

        self.peaks_cache = (num_px, mins, maxs)
        return mins, maxs

    # ------------------------------------------------------------------ #
    # Serialization helpers (audio bytes handled separately by project_io)
    # ------------------------------------------------------------------ #
    def to_meta_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "offset": self.offset,
            "gain": self.gain,
            "pan": self.pan,
            "mute": self.mute,
            "solo": self.solo,
            "loop_enabled": self.loop_enabled,
            "color": self.color,
            "effects": self.effects.to_dict(),
        }

    def load_meta_dict(self, d):
        self.id = d.get("id", self.id)
        self.name = d.get("name", self.name)
        self.offset = d.get("offset", 0)
        self.gain = d.get("gain", 1.0)
        self.pan = d.get("pan", 0.0)
        self.mute = d.get("mute", False)
        self.solo = d.get("solo", False)
        self.loop_enabled = d.get("loop_enabled", False)
        self.color = d.get("color", self.color)
        if "effects" in d:
            self.effects.from_dict(d["effects"])


def _resample_linear(data, src_sr, dst_sr):
    """Lightweight dependency-free linear-interpolation resampler, used only
    for imported files whose sample rate differs from the engine's rate."""
    if src_sr == dst_sr or len(data) == 0:
        return data
    duration = len(data) / float(src_sr)
    dst_len = int(round(duration * dst_sr))
    src_idx = np.linspace(0, len(data) - 1, dst_len)
    return np.interp(src_idx, np.arange(len(data)), data).astype(np.float32)
