"""
stream_config.py  (Live Looper Pro v2.0, Phase 1)

Pure-Python description of "how to open the audio stream" plus the fallback
ladder. It does NOT import sounddevice, so it is trivially testable.

The ladder (each step is tried in order until one opens):
    1. WASAPI exclusive at the chosen rate
    2. WASAPI exclusive at the other rate (44100 <-> 48000)
    3. Shared mode at 48000 Hz (or at the engine's current rate if tracks
       already exist, because tracks cache the sample rate)
    4. Fail with a clear message

Rate-change rule: the engine rate may only change while NO tracks exist.
"""

from dataclasses import dataclass, replace
from typing import List, Optional

DEFAULT_RATE = 48000
DEFAULT_BLOCK = 64
SUPPORTED_RATES = (44100, 48000)
WASAPI_NAME = "Windows WASAPI"


@dataclass(frozen=True)
class StreamConfig:
    api: str = WASAPI_NAME          # host API name the devices must belong to
    exclusive: bool = True          # WASAPI exclusive mode
    sample_rate: int = DEFAULT_RATE
    block_size: int = DEFAULT_BLOCK
    latency: str = "low"            # passed to sounddevice ("low" or seconds)
    in_device: Optional[int] = None
    out_device: Optional[int] = None
    channels_in: int = 1
    channels_out: int = 2
    split: bool = False             # exclusive: separate input + output streams (see split_stream.py)

    def mode_label(self) -> str:
        mode = "WASAPI EXCLUSIVE" if self.exclusive else "SHARED"
        if self.exclusive and self.split:
            mode += " SPLIT"
        return f"{mode} {self.sample_rate} Hz / {self.block_size}"

    def short_label(self) -> str:
        """Used in the 'Trying ...' log line, e.g. 'exclusive 48000/64'."""
        mode = "exclusive" if self.exclusive else "shared"
        if self.exclusive and self.split:
            mode += "-split"
        return f"{mode} {self.sample_rate}/{self.block_size}"


def other_rate(rate: int) -> int:
    return 44100 if rate == 48000 else 48000


def build_ladder(cfg: StreamConfig, tracks_exist: bool,
                 current_rate: int) -> List[StreamConfig]:
    """Return the ordered, de-duplicated list of configs to try."""
    steps: List[StreamConfig] = []

    if cfg.exclusive:
        steps.append(cfg)
        if not tracks_exist:
            steps.append(replace(cfg, sample_rate=other_rate(cfg.sample_rate)))
        shared_rate = current_rate if tracks_exist else DEFAULT_RATE
        steps.append(replace(cfg, exclusive=False, split=False, sample_rate=shared_rate))
    else:
        steps.append(cfg)

    unique: List[StreamConfig] = []
    for s in steps:
        if s not in unique:
            unique.append(s)
    return unique


def check_same_hostapi(cfg: StreamConfig, devices, hostapis) -> Optional[str]:
    """Exclusive mode needs input AND output on the WASAPI host API.
    Returns None if fine, otherwise a human-readable reason.
    `devices` / `hostapis` are the lists from sd.query_devices()/query_hostapis().
    """
    def api_of(idx):
        dev = devices[idx]
        return hostapis[dev["hostapi"]]["name"]

    try:
        in_api = api_of(cfg.in_device)
        out_api = api_of(cfg.out_device)
    except Exception as e:  # unknown device index etc.
        return f"could not look up device host API ({e})"

    if in_api != cfg.api or out_api != cfg.api:
        return (f"exclusive mode needs both devices on '{cfg.api}', but input is on "
                f"'{in_api}' and output is on '{out_api}'")
    return None
