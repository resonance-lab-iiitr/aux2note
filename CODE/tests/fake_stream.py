"""
FakeStream: drives AudioEngine._callback in a plain loop with synthetic input,
exactly the way PortAudio would, but with no sound card.
"""
import numpy as np
from tests import _stubs  # noqa: F401
from audio_engine import AudioEngine


def make_engine(sr=48000, block=64):
    e = AudioEngine(sample_rate=sr, block_size=block)
    # The routing / recording tests below check bit-exact audio paths, so the
    # rc10 input clean-up (DC blocker + expander) is switched off here and
    # tested on its own in tests/test_phase8_clean_audio.py.
    e.input_cleanup_enabled = False
    return e


def sine(n, sr=48000, freq=440.0, amp=0.3, start=0):
    t = (np.arange(n) + start) / float(sr)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def run_blocks(engine, in_signal, block=None):
    """Feed `in_signal` (mono float32) through the engine callback block by
    block. Returns (out_l, out_r) arrays of the same length (trailing partial
    block is dropped, like a real stream would never deliver one)."""
    block = block or engine.block_size
    nblocks = len(in_signal) // block
    out_l = np.zeros(nblocks * block, dtype=np.float32)
    out_r = np.zeros(nblocks * block, dtype=np.float32)
    for b in range(nblocks):
        indata = in_signal[b * block:(b + 1) * block].reshape(-1, 1).copy()
        outdata = np.zeros((block, 2), dtype=np.float32)
        engine._callback(indata, outdata, block, None, None)
        out_l[b * block:(b + 1) * block] = outdata[:, 0]
        out_r[b * block:(b + 1) * block] = outdata[:, 1]
    return out_l, out_r
