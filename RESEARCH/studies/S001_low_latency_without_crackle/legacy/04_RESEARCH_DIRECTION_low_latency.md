# Research direction: very low latency without crackle

## Goal (owner)
Round-trip latency of 10 to 20 ms, or lower, with no crackle, dropouts or other disturbance.

## What the numbers allow (estimates, not measurements)
One block lasts block / rate: 64 = 1.33 ms, 128 = 2.67 ms, 256 = 5.33 ms at 48000 Hz. A round trip needs at least an input block and an output block plus driver and converter buffering, so block 128 gives a floor of about 5 ms before driver overhead. The app's own text says shared mode is about 37 ms. So the 10 to 20 ms goal means a low-latency path: exclusive WASAPI, ASIO or WDM-KS. Real values must be measured (step 1).

## Status per path (from the data)
| Path | State |
|---|---|
| WASAPI shared 128 / 256 | clean (3 captures); slow (about 37 ms per the app) |
| MME 128 / 256 | clean (2 captures); slow |
| WASAPI exclusive 128 / 256 | 3 of 4 captures damaged; intermittent; engine output clean |
| ASIO4ALL v2 | installed, listed by the app (ID 10), never tested |
| WDM-KS | listed (IDs 14 to 18), never tested; the matrix tool has a `wdmks` key |
| DirectSound | never tested |
| Other device (USB headset or interface) | not available yet |

## Plan, in order (one change at a time; 3 captures per setting; UNMOUNT before ANALYZE)
1. **Measure latency** of what works now: `python latency_lab.py --help`, then for example `python latency_lab.py run --api WASAPI ASIO --blocks 64 128 256` (usage line from that file's header; not run by us). Record the number per mode.
2. **Is the fault decided at stream open?** Exclusive 256: mount, Lab test tone 10 s, unmount; repeat 5 times. Count how many are bad.
3. **Range of exclusive:** `run_crackle_matrix.bat --scenarios S3 --apis wasapi-excl --rates 44100,48000 --blocks 64,128,256,512 --yes --out captures\matrix_S3_excl_full`; run it twice.
4. **Windows variables** (re-run Lab tone exclusive 256 after each): untick "Give exclusive mode applications priority"; Realtek enhancements off; change the device format from 24 bit to 16 bit at 48000 Hz (tests the format conversion hypothesis, not proven); Microsoft "High Definition Audio Device" driver instead of the Realtek one; note the Realtek driver version; power plan high performance.
5. **ASIO4ALL:** open its control panel, set the buffer to 128 or 256 samples, Lab test tone, 3 captures. It sits on top of the Windows drivers, so it may inherit the same fault; the result tells us.
6. **WDM-KS and DirectSound:** matrix `--apis wdmks,directsound` with S3.
7. **Other hardware:** any USB audio device with its own driver (ideally ASIO): Lab test tone exclusive / ASIO at 128 and 64. If clean, the fault is specific to the onboard Realtek path and a dedicated interface is the way to 10 ms and below.
8. **Program side (Claude, later):** test opening 2 input channels for the stereo Line In (the program opens 1); check which stream arguments exclusive mode receives in `audio_engine.py`; cards for tool defects D-1 to D-10 first so verdicts can be trusted.

## What counts as success (proposed thresholds, to be agreed)
Tone error better than -55 dB and 0 bursts per second in 3 consecutive 20 s captures at the target block size, no late blocks, and a measured round trip of 20 ms or less (10 ms as the stretch goal).

## Decision rule after the tests
- Some exclusive or ASIO setting is clean 3 of 3: adopt it, make it the default in the app, record the settings.
- Only shared / MME stay clean on this Realtek: the onboard path cannot give the goal; use shared for normal work and get a USB interface for low latency.
- A USB device is also faulty in exclusive mode: investigate the program's stream opening (software) next.

## Work already planned in the project (v036)
DOC fold (doc lag 3), then PLAN: tool fixes D-1 to D-10 and this research phase; then T025 declicker (repair of damaged recordings, not a cure for exclusive mode).

## What to send back after testing
For each Lab capture: `raw.wav`, `output.wav`, `analysis\report.md`; any `matrix_summary.md/csv`; the latency numbers; `notes.txt` (jack colours, Windows volume, Realtek driver version, what you heard, errors word for word); the app log `looper.log`.
