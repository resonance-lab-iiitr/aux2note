"""
settings_store.py  (Live Looper Pro v2.0, Phase 4b)

Pure Python (no Tk, no sounddevice): everything the audio settings panel
decides, so it can be tested without a window or a sound card.

  * settings.json  load / save (a missing or broken file is ignored)
  * device-list helpers (filter by driver, pick defaults, parse "ID 3: ...")
  * build_config(): panel choices -> StreamConfig
"""

import json
import os
from dataclasses import replace

from stream_config import StreamConfig, WASAPI_NAME, SUPPORTED_RATES

BLOCK_SIZES = (32, 64, 128, 160, 256, 512)
MAX_OFFSET_MS = 500.0
UI_SCALE_MIN, UI_SCALE_MAX = 0.8, 2.0     # same range as ui_theme.set_scale

# AUTO / default block size. 128 is BAD on the test PC with split exclusive streams
# (about 4000 clicks/min in split_test.py); 160 is the documented clean size.
# Change this one number after more split_test.py runs.
AUTO_BLOCK = 160
# Bump when the audio defaults change. A settings.json without this number is from an older
# version: its "split" and block 128 are replaced by the new defaults once.
AUDIO_DEFAULTS_VERSION = 2

DEFAULT_SETTINGS = {
    "driver": WASAPI_NAME,
    "exclusive": True,
    "audio_defaults": AUDIO_DEFAULTS_VERSION,
    "split": True,        # exclusive with separate input/output streams (a single exclusive duplex stream crackles on the test PC)
    "sample_rate": 48000,
    "block_size": AUTO_BLOCK,
    "record_offset_ms": 0.0,
    "in_device": "",     # device NAME (ids change between boots)
    "out_device": "",
    "calibration": None,  # {"rtt_ms": float, "key": "WASAPI EXCL 48000/64"} or None
    "ui_scale": 1.0,      # GUI scale factor 0.8-2.0 (Ctrl +, Ctrl -, Ctrl 0)
}


def default_settings_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


# --------------------------------------------------------------------------- #
# settings.json
# --------------------------------------------------------------------------- #
def sanitize(data):
    """Return a complete, valid settings dict. Anything wrong falls back to
    the default for that key; unknown keys are dropped."""
    out = dict(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return out
    d = data
    if isinstance(d.get("driver"), str) and d["driver"]:
        out["driver"] = d["driver"]
    if isinstance(d.get("exclusive"), bool):
        out["exclusive"] = d["exclusive"]
    legacy = d.get("audio_defaults") != AUDIO_DEFAULTS_VERSION
    if isinstance(d.get("split"), bool) and not legacy:
        out["split"] = d["split"]
    if d.get("sample_rate") in SUPPORTED_RATES and not isinstance(d.get("sample_rate"), bool):
        out["sample_rate"] = d["sample_rate"]
    if (d.get("block_size") in BLOCK_SIZES and not isinstance(d.get("block_size"), bool)
            and not (legacy and d.get("block_size") == 128)):
        out["block_size"] = d["block_size"]
    off = d.get("record_offset_ms")
    if isinstance(off, (int, float)) and not isinstance(off, bool) and 0.0 <= off <= MAX_OFFSET_MS:
        out["record_offset_ms"] = float(off)
    sc = d.get("ui_scale")
    if (isinstance(sc, (int, float)) and not isinstance(sc, bool)
            and sc == sc and UI_SCALE_MIN <= sc <= UI_SCALE_MAX):
        out["ui_scale"] = round(float(sc), 2)
    for k in ("in_device", "out_device"):
        if isinstance(d.get(k), str):
            out[k] = d[k]
    c = d.get("calibration")
    if (isinstance(c, dict) and isinstance(c.get("key"), str) and c["key"]
            and isinstance(c.get("rtt_ms"), (int, float)) and not isinstance(c.get("rtt_ms"), bool)
            and 0.0 < c["rtt_ms"] <= MAX_OFFSET_MS):
        out["calibration"] = {"rtt_ms": float(c["rtt_ms"]), "key": c["key"]}
    return out


def load_settings(path=None):
    path = path or default_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sanitize(json.load(f))
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings, path=None):
    """Returns True on success. Never raises (settings are best-effort)."""
    path = path or default_settings_path()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sanitize(settings), f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Device lists. Entries are (id, label) with label "ID 3: Name  [Driver]".
# --------------------------------------------------------------------------- #
def driver_of(label):
    return label.rsplit("[", 1)[-1].rstrip("] ").strip() if "[" in label else ""


def name_of(label):
    """'ID 3: Speakers (Realtek)  [Windows WASAPI]' -> 'Speakers (Realtek)'"""
    body = label.split(":", 1)[1] if ":" in label else label
    if "[" in body:
        body = body.rsplit("[", 1)[0]
    return body.strip()


def parse_device_id(label):
    return int(label.split(":")[0].split(" ")[1])


def driver_names(entries):
    seen = []
    for _, label in entries:
        d = driver_of(label)
        if d and d not in seen:
            seen.append(d)
    return seen


def filter_by_driver(entries, driver):
    return [(i, l) for i, l in entries if driver_of(l) == driver]


def default_device_ids(hostapis, sd_default):
    """(input_ids, output_ids): the default device of EVERY host API (MME, DirectSound,
    WASAPI, ...) plus the sounddevice default pair. Needed because the plain Windows
    default is an MME device, so on its own it never matches a WASAPI device and the
    AUTO button then picked the first WASAPI device in the list (for example a webcam
    microphone that only supports 16000 Hz)."""
    ins, outs = set(), set()
    for api in hostapis or []:
        di, do = api.get("default_input_device"), api.get("default_output_device")
        if isinstance(di, int) and di >= 0:
            ins.add(di)
        if isinstance(do, int) and do >= 0:
            outs.add(do)
    try:
        di, do = sd_default
        if isinstance(di, int) and di >= 0:
            ins.add(di)
        if isinstance(do, int) and do >= 0:
            outs.add(do)
    except Exception:
        pass
    return ins, outs


def _same_device_name(a, b):
    """MME cuts device names at 31 characters, so compare as prefixes too."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 12 and (a.startswith(b) or b.startswith(a)))


def preferred_index(entries, rows, default_key):
    """Index of the entry to preselect: the default device if it is in the list,
    else a device whose name matches a default device's name (also when MME cut the
    name short), else 0."""
    default_ids = {r["id"] for r in rows if r.get(default_key)}
    for i, (dev_id, _) in enumerate(entries):
        if dev_id in default_ids:
            return i
    names = [r["name"] for r in rows if r["id"] in default_ids]
    for i, (_, label) in enumerate(entries):
        if any(_same_device_name(name_of(label), n) for n in names):
            return i
    return 0


def index_by_name(entries, name):
    """Index of the entry whose device name matches `name`, or None."""
    if not name:
        return None
    for i, (_, label) in enumerate(entries):
        if name_of(label) == name:
            return i
    return None


# --------------------------------------------------------------------------- #
# Panel choices -> StreamConfig / samples
# --------------------------------------------------------------------------- #
def is_wasapi(driver):
    return driver == WASAPI_NAME


def build_config(driver, exclusive, rate, block, in_id, out_id, split=False):
    """Exclusive only exists on WASAPI; on any other driver it is forced off."""
    return StreamConfig(api=driver, exclusive=bool(exclusive) and is_wasapi(driver),
                        sample_rate=int(rate), block_size=int(block),
                        in_device=in_id, out_device=out_id,
                        split=bool(split) and bool(exclusive) and is_wasapi(driver))


def parse_offset_ms(text):
    """Text from the entry box -> ms (0..500). Bad text -> None."""
    try:
        v = float(str(text).strip().replace(",", "."))
    except ValueError:
        return None
    if v != v or v < 0.0 or v > MAX_OFFSET_MS:
        return None
    return v


def ms_to_samples(ms, sample_rate):
    return max(0, int(round(ms * sample_rate / 1000.0)))


def auto_choice():
    """The AUTO (recommended) button: WASAPI exclusive, split in/out streams, 48000 / AUTO_BLOCK (160).

    128 was chosen from real-PC measurements: round trip 9.6 ms (target 12 ms) and a
    10-minute soak with typical effects had 0 late blocks. Block 64 had rare late blocks
    with all effects on; block 256 is the cleanest but its round trip is 12.3 ms."""
    return dict(driver=WASAPI_NAME, exclusive=True, split=True, sample_rate=48000,
                block_size=AUTO_BLOCK)
