"""
capture_recorder.py  (Live Looper Pro, Phase 10 Crackle Lab, T020)

A raw tap on the audio callback. It stores EXACTLY what the sound card hands
to the callback (every input channel, float32, before CLEAN INPUT or any
effect) and, for every block, the timing facts needed to tell hardware from
software (D021):

    index        block number, 0, 1, 2 ...
    start        first sample index of the block inside raw.wav
    frames       frames in the block
    cb_ms        how long the callback ran, milliseconds
    status       PortAudio flags: 1 input underflow, 2 input overflow,
                 4 output underflow, 8 output overflow (0 = fine)
    adc_time     PortAudio inputBufferAdcTime of the block, seconds (nan if unknown)
    adc_err_ms   (adc_time step from the previous block) - (previous frames / rate),
                 milliseconds; 0 for a perfect clock, nan for the first block
    current_time PortAudio currentTime, seconds (nan if unknown)
    output_time  PortAudio outputBufferDacTime, seconds (nan if unknown)
    t_start      time.perf_counter() at the start of the callback, seconds

The column names `start frames cb_ms status adc_time` are what crackle_core
reads (D045). T019 and T022 depend on them.

Real-time rules (the audio thread calls `feed`): no lock, no logging, no
allocation beyond a few Python floats. Every array is preallocated in
__init__. When a buffer is full, capture stops by itself and `full` becomes
True; nothing ever grows. Files are written from the UI thread by `to_files`.
"""

import gzip
import json
import math
import os
import time

import numpy as np

STATUS_INPUT_UNDERFLOW = 1
STATUS_INPUT_OVERFLOW = 2
STATUS_OUTPUT_UNDERFLOW = 4
STATUS_OUTPUT_OVERFLOW = 8

BLOCK_COLUMNS = ("index", "start", "frames", "cb_ms", "status", "adc_time",
                 "adc_err_ms", "current_time", "output_time", "t_start")

_NAN = float("nan")


class CaptureRecorder:
    def __init__(self, sample_rate, block_size, channels_in=1, channels_out=2,
                 max_seconds=120, capture_output=False):
        self.sample_rate = int(sample_rate)
        self.block_size = int(block_size)
        self.channels_in = max(1, int(channels_in))
        self.channels_out = max(1, int(channels_out))
        self.capture_output = bool(capture_output)
        self.max_frames = max(1, int(round(max_seconds * self.sample_rate)))
        bs = max(1, self.block_size)
        # Room for twice the nominal number of blocks, so blocks smaller than
        # block_size (some drivers) do not stop the capture early.
        self.max_blocks = 2 * (-(-self.max_frames // bs)) + 16

        self.raw = np.zeros((self.max_frames, self.channels_in), dtype=np.float32)
        self.out = (np.zeros((self.max_frames, self.channels_out), dtype=np.float32)
                    if self.capture_output else None)

        n = self.max_blocks
        self.b_start = np.zeros(n, dtype=np.int64)
        self.b_frames = np.zeros(n, dtype=np.int32)
        self.b_cb_ms = np.zeros(n, dtype=np.float32)
        self.b_status = np.zeros(n, dtype=np.int8)
        self.b_adc = np.zeros(n, dtype=np.float64)
        self.b_adc_err_ms = np.zeros(n, dtype=np.float32)
        self.b_cur = np.zeros(n, dtype=np.float64)
        self.b_out_t = np.zeros(n, dtype=np.float64)
        self.b_t0 = np.zeros(n, dtype=np.float64)

        self.active = True           # False once stopped or full
        self.full = False
        self.n_blocks = 0
        self.n_frames = 0
        self._prev_adc = _NAN
        self._prev_frames = 0
        self.created = time.time()

    # ------------------------------------------------------------------ #
    # Audio thread
    # ------------------------------------------------------------------ #
    def feed(self, indata, outdata, frames, time_info, status, t_start, t_end):
        """Store one block. Called once per callback, after the engine body has
        run (so `outdata` is final). Never raises into the audio thread."""
        if not self.active:
            return
        nb = self.n_blocks
        pos = self.n_frames
        end = pos + frames
        if nb >= self.max_blocks or end > self.max_frames:
            self.full = True
            self.active = False
            return
        try:
            ci = indata.shape[1]
            if ci >= self.channels_in:
                self.raw[pos:end] = indata[:frames, :self.channels_in]
            elif ci > 0:
                self.raw[pos:end, :ci] = indata[:frames]
            if self.out is not None and outdata is not None:
                co = min(outdata.shape[1], self.channels_out)
                self.out[pos:end, :co] = outdata[:frames, :co]

            status_bits = 0
            if status:
                if getattr(status, "input_underflow", False):
                    status_bits |= STATUS_INPUT_UNDERFLOW
                if getattr(status, "input_overflow", False):
                    status_bits |= STATUS_INPUT_OVERFLOW
                if getattr(status, "output_underflow", False):
                    status_bits |= STATUS_OUTPUT_UNDERFLOW
                if getattr(status, "output_overflow", False):
                    status_bits |= STATUS_OUTPUT_OVERFLOW

            adc = cur = dac = _NAN
            if time_info is not None:
                adc = float(getattr(time_info, "inputBufferAdcTime", _NAN))
                cur = float(getattr(time_info, "currentTime", _NAN))
                dac = float(getattr(time_info, "outputBufferDacTime", _NAN))
            prev = self._prev_adc
            if prev == prev and adc == adc:      # neither is nan
                err = ((adc - prev) - self._prev_frames / self.sample_rate) * 1000.0
            else:
                err = _NAN
            self._prev_adc = adc
            self._prev_frames = frames

            self.b_start[nb] = pos
            self.b_frames[nb] = frames
            self.b_cb_ms[nb] = (t_end - t_start) * 1000.0
            self.b_status[nb] = status_bits
            self.b_adc[nb] = adc
            self.b_adc_err_ms[nb] = err
            self.b_cur[nb] = cur
            self.b_out_t[nb] = dac
            self.b_t0[nb] = t_start
            self.n_blocks = nb + 1
            self.n_frames = end
        except Exception:                      # never break the audio thread
            self.active = False

    # ------------------------------------------------------------------ #
    # UI thread
    # ------------------------------------------------------------------ #
    def stop(self):
        self.active = False

    @property
    def seconds(self):
        return self.n_frames / float(self.sample_rate)

    def captured_input(self):
        """View of the captured input, shape (frames, channels_in)."""
        return self.raw[:self.n_frames]

    def blocks_table(self):
        """The per-block table as a dict of numpy arrays (copies)."""
        n = self.n_blocks
        return {
            "index": np.arange(n, dtype=np.int64),
            "start": self.b_start[:n].copy(),
            "frames": self.b_frames[:n].copy(),
            "cb_ms": self.b_cb_ms[:n].copy(),
            "status": self.b_status[:n].astype(np.int64),
            "adc_time": self.b_adc[:n].copy(),
            "adc_err_ms": self.b_adc_err_ms[:n].copy(),
            "current_time": self.b_cur[:n].copy(),
            "output_time": self.b_out_t[:n].copy(),
            "t_start": self.b_t0[:n].copy(),
        }

    def to_files(self, folder, extra_meta=None):
        """Write raw.wav (float32, all input channels), output.wav (only when
        capture_output), blocks.csv.gz and meta.json into `folder` (created if
        needed). Returns {name: path}. Call from the UI thread after stop()."""
        import soundfile as sf

        self.stop()
        os.makedirs(folder, exist_ok=True)
        paths = {}

        paths["raw"] = os.path.join(folder, "raw.wav")
        sf.write(paths["raw"], self.captured_input(), self.sample_rate, subtype="FLOAT")
        if self.out is not None:
            paths["output"] = os.path.join(folder, "output.wav")
            sf.write(paths["output"], self.out[:self.n_frames], self.sample_rate, subtype="FLOAT")

        t = self.blocks_table()
        paths["blocks"] = os.path.join(folder, "blocks.csv.gz")
        with gzip.open(paths["blocks"], "wt", newline="") as fh:
            fh.write(",".join(BLOCK_COLUMNS) + "\n")
            cols = [t[c] for c in BLOCK_COLUMNS]
            for i in range(self.n_blocks):
                fh.write("%d,%d,%d,%.6f,%d,%.9f,%.6f,%.9f,%.9f,%.9f\n" % (
                    cols[0][i], cols[1][i], cols[2][i], cols[3][i], cols[4][i],
                    cols[5][i], cols[6][i], cols[7][i], cols[8][i], cols[9][i]))

        meta = {
            "format": "live-looper-capture-1",
            "created_unix": self.created,
            "sample_rate": self.sample_rate,
            "block_size": self.block_size,
            "channels_in": self.channels_in,
            "channels_out": self.channels_out,
            "capture_output": self.capture_output,
            "frames": int(self.n_frames),
            "seconds": round(self.seconds, 6),
            "blocks": int(self.n_blocks),
            "full": bool(self.full),
            "status_blocks": int(np.count_nonzero(self.b_status[:self.n_blocks])),
            "raw_note": "raw.wav is the exact sound card input before CLEAN INPUT and effects.",
            "status_bits": {"1": "input underflow", "2": "input overflow",
                            "4": "output underflow", "8": "output overflow"},
        }
        if extra_meta:
            meta.update(extra_meta)
        paths["meta"] = os.path.join(folder, "meta.json")
        with open(paths["meta"], "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, default=_json_default)
        return paths


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if math.isnan(v) else v
    return str(o)
