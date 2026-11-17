"""
project_io.py
- Save / load full projects as a single re-openable ".llproj" file (a zip
  bundle containing project.json + one WAV per track, so nothing is lossy
  and everything can be edited again next time).
- Render and export the final mixdown to WAV (always available) or MP3
  (via the pure-Python `lameenc` encoder, no external ffmpeg binary needed).
"""

import io
import json
import zipfile

import numpy as np
import soundfile as sf

from track import Track
from effects import soft_limit
from version import APP_VERSION

PROJECT_VERSION = 1   # file FORMAT version (unchanged, old files still load)
RENDER_BLOCK = 2048


# --------------------------------------------------------------------------- #
# Project save / load
# --------------------------------------------------------------------------- #
def save_project(path, engine):
    """Snapshots engine state under the engine lock before writing to disk,
    so a save can never race against the realtime callback mutating tracks
    (e.g. a recording committing its buffer) mid-write."""
    with engine.lock:
        tracks_snapshot = list(engine.tracks)
        data = {
            "version": PROJECT_VERSION,
            "app_version": APP_VERSION,
            "sample_rate": engine.sample_rate,
            "audio": {"sample_rate": engine.sample_rate, "block_size": engine.block_size},
            "loop_enabled": engine.loop_enabled,
            "loop_start": engine.loop_start,
            "loop_end": engine.loop_end,
            "master_gain": engine.master_gain,
            "master_fx": engine.master_fx_l.to_dict(),
            "input_monitor_enabled": engine.input_monitor_enabled,
            "record_with_output_enabled": engine.record_with_output_enabled,
            "monitor_gain": engine.monitor_gain,
            "tracks": [],
        }
        track_audio = []
        for i, t in enumerate(tracks_snapshot):
            wav_name = f"track_{i:02d}_{t.id}.wav"
            audio = t.buffer.copy() if t.length > 0 else np.zeros(1, dtype=np.float32)
            track_audio.append((wav_name, audio))
            meta = t.to_meta_dict()
            meta["audio_file"] = wav_name
            data["tracks"].append(meta)

    # The actual (potentially slow) disk I/O happens outside the lock so we
    # don't block the realtime audio thread any longer than necessary.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for wav_name, audio in track_audio:
            buf = io.BytesIO()
            sf.write(buf, audio, engine.sample_rate, format="WAV", subtype="FLOAT")
            zf.writestr(wav_name, buf.getvalue())
        zf.writestr("project.json", json.dumps(data, indent=2))


def load_project(path, sample_rate_hint=48000):
    """Returns (tracks, transport_settings_dict)."""
    tracks = []
    with zipfile.ZipFile(path, "r") as zf:
        data = json.loads(zf.read("project.json").decode("utf-8"))
        sr = data.get("sample_rate", sample_rate_hint)

        for meta in data["tracks"]:
            t = Track(meta.get("name", "Track"), sr)
            wav_bytes = zf.read(meta["audio_file"])
            audio, file_sr = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            t.buffer = audio.astype(np.float32)
            t.load_meta_dict(meta)
            tracks.append(t)

    transport = {
        "loop_enabled": data.get("loop_enabled", False),
        "loop_start": data.get("loop_start", 0),
        "loop_end": data.get("loop_end", 0),
        "master_gain": data.get("master_gain", 1.0),
        "master_fx": data.get("master_fx"),
        "input_monitor_enabled": data.get("input_monitor_enabled", False),
        "record_with_output_enabled": data.get("record_with_output_enabled", False),
        "monitor_gain": data.get("monitor_gain", 1.0),
        "sample_rate": sr,
        # Phase 4b: old files have no "audio" section -> rate from the file,
        # block size left to the user's current setting ("present" False).
        "audio": {
            "sample_rate": (data.get("audio") or {}).get("sample_rate", sr),
            "block_size": (data.get("audio") or {}).get("block_size", 64),
            "present": isinstance(data.get("audio"), dict),
        },
    }
    return tracks, transport


# --------------------------------------------------------------------------- #
# Offline mixdown rendering (does not touch the live realtime effect state)
# --------------------------------------------------------------------------- #
def render_mix(tracks, sample_rate, loop_count=1, master_gain=1.0, master_fx=None, extra_tail_sec=1.5):
    """`tracks` should be a stable snapshot (see AudioEngine.snapshot_tracks)
    taken by the caller, not a live reference to engine.tracks, since this
    runs on a background thread while the realtime thread may still be
    adding/removing tracks."""
    if not tracks:
        return np.zeros((sample_rate, 2), dtype=np.float32)

    arrangement_len = max((t.end_offset for t in tracks), default=0)
    total_len = max(1, arrangement_len * max(1, loop_count) + int(extra_tail_sec * sample_rate))

    # Clone effect chains so live playback state is never disturbed by rendering
    chains = [t.effects.clone() for t in tracks]
    fx_l = master_fx.clone() if master_fx is not None else None
    fx_r = master_fx.clone() if master_fx is not None else None

    # Respect SOLO exactly the way the live engine does: if any track is
    # soloed, only soloed (and unmuted) tracks are audible. The exported
    # mixdown must match what was actually monitored during playback.
    any_solo = any(t.solo for t in tracks)

    out_l = np.zeros(total_len, dtype=np.float32)
    out_r = np.zeros(total_len, dtype=np.float32)

    pos = 0
    while pos < total_len:
        n = min(RENDER_BLOCK, total_len - pos)
        block_l = np.zeros(n, dtype=np.float32)
        block_r = np.zeros(n, dtype=np.float32)

        for loop_idx in range(max(1, loop_count)):
            timeline_pos = pos - loop_idx * arrangement_len
            if timeline_pos + n <= 0 or timeline_pos >= arrangement_len:
                continue
            for t, chain in zip(tracks, chains):
                active = (not t.mute) and (not any_solo or t.solo)
                if not active:
                    continue
                samples = t.get_samples(timeline_pos, n)
                if np.any(samples):
                    samples = chain.process(samples)
                pan = max(-1.0, min(1.0, t.pan))
                l_gain = t.gain * (1.0 - max(pan, 0.0))
                r_gain = t.gain * (1.0 + min(pan, 0.0))
                block_l += samples * l_gain
                block_r += samples * r_gain

        # Full master chain (EQ / compressor / distortion / delay / reverb),
        # matching what the live engine applies - an exported file must
        # sound identical to what was actually monitored during playback.
        if fx_l is not None:
            block_l = fx_l.process(block_l)
            block_r = fx_r.process(block_r)

        out_l[pos:pos + n] = block_l * master_gain
        out_r[pos:pos + n] = block_r * master_gain
        pos += n

    out_l = soft_limit(out_l)
    out_r = soft_limit(out_r)
    return np.stack([out_l, out_r], axis=1)


def export_wav(path, stereo_float, sample_rate):
    sf.write(path, stereo_float, sample_rate, format="WAV", subtype="PCM_24")


def export_mp3(path, stereo_float, sample_rate, bitrate=192):
    import lameenc

    pcm = np.clip(stereo_float, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(2)
    encoder.set_quality(2)

    mp3_data = encoder.encode(pcm16.tobytes())
    mp3_data += encoder.flush()

    with open(path, "wb") as f:
        f.write(mp3_data)
