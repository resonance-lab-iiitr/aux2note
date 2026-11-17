"""
split_stream.py

Opens ONE input stream and ONE output stream (two separate PortAudio streams)
and presents them to the engine like a single duplex stream.

Why: on this PC (Microsoft HD Audio driver) a single exclusive DUPLEX stream
is always bad, but two separate exclusive streams are clean at block 160 and
256 (measured with excl_probe.py, variant split_2ch).

How: the input callback writes the left channel (channel 0) into a small
ring buffer. The OUTPUT callback is the clock: each time it runs it takes
`frames` samples from the ring and calls the engine callback
    callback(indata (frames,1), outdata, frames, time_info, status)
which is exactly the duplex signature, so the engine code does not change.

Added latency: PREFILL_BLOCKS blocks (default 1) of buffering in the ring.
If the input runs late, one block of silence is used and counted as underflow.
No locks: one writer (input thread) and one reader (output thread).
"""
import os
import time

import numpy as np
import sounddevice as sd

PREFILL_BLOCKS = 1      # blocks buffered before the output starts reading
RING_BLOCKS = 16        # ring size in blocks
TRACE_EVENTS = 40000    # timing trace: callbacks kept (about 60 s at block 160)


class SplitStream:
    def __init__(self, in_device, out_device, samplerate, blocksize,
                 channels_out, callback, latency="low", exclusive=True,
                 prefill_blocks=PREFILL_BLOCKS):
        self._cb = callback
        self.block = int(blocksize)
        self.channels_out = int(channels_out)
        self.prefill = max(1, int(prefill_blocks)) * self.block
        self.cap = RING_BLOCKS * self.block
        self._ring = np.zeros(self.cap, dtype=np.float32)
        self._w = 0                    # total samples written (input thread only)
        self._r = 0                    # total samples read (output thread only)
        self._primed = False
        self._in_scratch = np.zeros((self.block, 1), dtype=np.float32)
        self.underflows = 0
        self.overflows = 0
        self.trims = 0
        self.out_blocks = 0            # output callbacks that ran after priming
        self.in_blocks = 0
        # timing trace (written to logs/split_timing_<time>.csv on close)
        self._tn = 0
        self._t = np.zeros(TRACE_EVENTS, dtype=np.float64)   # perf_counter seconds
        self._k = np.zeros(TRACE_EVENTS, dtype=np.int8)      # 0 input cb, 1 output cb
        self._f = np.zeros(TRACE_EVENTS, dtype=np.int32)     # ring fill (samples) at callback start
        self._u = np.zeros(TRACE_EVENTS, dtype=np.int8)      # 1 = output cb used silence (underflow)
        self._a = np.full(TRACE_EVENTS, np.nan, dtype=np.float64)  # input cb: driver ADC time (s), nan if unknown
        self._c = np.zeros(TRACE_EVENTS, dtype=np.float64)   # input cb: sum of channel 0 (repeat detector)
        self.in_frames_total = 0       # T031: frames the input callbacks delivered (compare with wall time x rate)
        self.in_dup_blocks = 0         # T031: input blocks identical to the previous one (and not silent)
        self._last_chk = 0.0
        self.trace_path = None
        self.summary = ""

        ex = (sd.WasapiSettings(exclusive=True) if exclusive else None)
        common = dict(samplerate=samplerate, blocksize=self.block, dtype="float32")
        if exclusive:
            common["latency"] = latency
        # Input is opened with 2 channels (the Line In is stereo); we use channel 0.
        self._in = sd.InputStream(device=in_device, channels=2, callback=self._in_cb,
                                  extra_settings=ex, **common)
        self._out = sd.OutputStream(device=out_device, channels=self.channels_out,
                                    callback=self._out_cb, extra_settings=ex, **common)

    # ----------------------------------------------------------------- callbacks
    def _trace(self, kind, fill, under=0, adc=float("nan"), chk=0.0):
        n = self._tn
        if n < TRACE_EVENTS:
            self._t[n] = time.perf_counter()
            self._k[n] = kind
            self._f[n] = fill
            self._u[n] = under
            self._a[n] = adc
            self._c[n] = chk
            self._tn = n + 1

    def _in_cb(self, indata, frames, time_info, status):
        w = self._w
        self.in_blocks += 1
        self.in_frames_total += frames
        try:
            adc = float(getattr(time_info, "inputBufferAdcTime", float("nan")))
        except Exception:
            adc = float("nan")
        chk = float(indata[:frames, 0].sum())
        if chk != 0.0 and chk == self._last_chk:
            self.in_dup_blocks += 1
        self._last_chk = chk
        self._trace(0, w - self._r, 0, adc, chk)
        if w - self._r + frames > self.cap:
            self.overflows += 1        # reader is too slow: drop this block
            return
        pos = w % self.cap
        first = min(frames, self.cap - pos)
        self._ring[pos:pos + first] = indata[:first, 0]
        if first < frames:
            self._ring[:frames - first] = indata[first:frames, 0]
        self._w = w + frames

    def _out_cb(self, outdata, frames, time_info, status):
        r = self._r
        fill = self._w - r
        self._trace(1, fill, 1 if (self._primed and fill < frames) else 0)
        if not self._primed:
            if fill >= self.prefill:
                self._primed = True
            else:
                outdata.fill(0.0)
                return
        self.out_blocks += 1
        # keep latency bounded: if the ring grew (clock drift), skip ahead
        if fill > self.prefill + 4 * self.block:
            r = self._w - self.prefill
            fill = self.prefill
            self.trims += 1
        buf = self._in_scratch
        if buf.shape[0] != frames:
            buf = self._in_scratch = np.zeros((frames, 1), dtype=np.float32)
        st = status
        if fill >= frames:
            pos = r % self.cap
            first = min(frames, self.cap - pos)
            buf[:first, 0] = self._ring[pos:pos + first]
            if first < frames:
                buf[first:frames, 0] = self._ring[:frames - first]
            self._r = r + frames
        else:
            buf.fill(0.0)              # input late: silence, count it
            self.underflows += 1
            self._r = r
        self._cb(buf, outdata, frames, time_info, st)

    # ----------------------------------------------------------------- stream-like API
    def start(self):
        self._in.start()
        self._out.start()

    def stop(self):
        for s in (self._out, self._in):
            try:
                s.stop()
            except Exception:
                pass

    def stats(self):
        """Counters for the Debug tab and the Lab meta.json (plain ints, safe to read any time)."""
        return {"split": True, "block": self.block, "prefill_blocks": self.prefill // self.block,
                "ring_blocks": self.cap // self.block, "underflows": int(self.underflows),
                "overflows": int(self.overflows), "trims": int(self.trims),
                "out_blocks": int(self.out_blocks), "in_blocks": int(self.in_blocks),
                "in_frames_total": int(self.in_frames_total), "in_dup_blocks": int(self.in_dup_blocks)}

    def write_trace(self, folder=None):
        """Save the callback timing trace; returns the path (or None)."""
        n = self._tn
        if n == 0:
            return None
        folder = folder or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "split_timing_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))
            t0 = self._t[0]
            with open(path, "w") as f:
                f.write("t_ms,kind,fill_samples,underflow,adc_ms,chk\n")
                a0 = next((x for x in self._a[:n] if x == x), float("nan"))
                for i in range(n):
                    adc = ("%.3f" % ((self._a[i] - a0) * 1000.0)) if self._a[i] == self._a[i] else ""
                    chk = ("%.6g" % self._c[i]) if self._k[i] == 0 else ""
                    f.write("%.3f,%s,%d,%d,%s,%s\n" % ((self._t[i] - t0) * 1000.0,
                            "in" if self._k[i] == 0 else "out", self._f[i], self._u[i], adc, chk))
            self.trace_path = path
        except Exception:
            self.trace_path = None
        return self.trace_path

    def close(self):
        self.summary = ("SPLIT STREAM: block %d, prefill %d, underflows %d, overflows %d, trims %d"
                        % (self.block, self.prefill // self.block, self.underflows, self.overflows, self.trims))
        self.summary += ", input frames %d, repeated input blocks %d" % (self.in_frames_total, self.in_dup_blocks)
        self.write_trace()
        for s in (self._out, self._in):
            try:
                s.close()
            except Exception:
                pass

    @property
    def latency(self):
        """(input, output) seconds as REPORTED by the driver, plus the ring
        prefill added to the input side. Not a measurement."""
        li = float(self._in.latency)
        lo = float(self._out.latency)
        return (li + self.prefill / float(self._in.samplerate), lo)

    @property
    def cpu_load(self):
        return max(float(self._in.cpu_load), float(self._out.cpu_load))


def split_meta(start, end):
    """Lab meta.json fields for one capture: the counters now minus the counters at the start.
    `start` / `end` are stats() dicts (or None). Returns {} when the engine is not in split mode."""
    if not end:
        return {}
    start = start or {}
    d = lambda k: max(0, int(end.get(k, 0)) - int(start.get(k, 0)))
    return {"split": True, "split_prefill_blocks": int(end.get("prefill_blocks", 0)),
            "split_ring_blocks": int(end.get("ring_blocks", 0)),
            "split_underflows": d("underflows"), "split_overflows": d("overflows"),
            "split_trims": d("trims"), "split_out_blocks": d("out_blocks")}
