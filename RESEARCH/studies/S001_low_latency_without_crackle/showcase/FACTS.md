# S001 facts (generated 2026-11-14 by `research.py showcase`; do not edit, edit SHOWCASE.md)

Study: Low latency without crackle | type investigate | status planning | stage 0 | depth deep | instrument untrusted

| What | Count |
|---|---|
| Hypotheses | 8 (7 open, 1 supported) |
| Experiments | 8 (3 analyzed, 5 planned); retroactive: 3 |
| Evidence runs | 14 (analyzed 14) |
| Findings | 23 (confidence: 23 low; status: 5 closed, 3 defect, 15 open) |
| Gates | 3 (3 pending) |

**Instrument is untrusted: every claim below is capped at low confidence.**

## Claims the study currently allows (from findings.csv)

| Id | Claim | Confidence | Status | Evidence |
|---|---|---|---|---|
| F-01 | Matrix tool / capture tap / analysis report run on the real PC and give readable packs [legacy confidence: high; legacy status: closed; imported 2026-11-14, capped at low while the instrument is untrusted] | low | closed | V003,V010,V011,V012,V013 |
| F-02 | S1: WASAPI excl+shared failed at 48000 Hz (PaErrorCode -9997 Invalid sample rate); S3 after Line In default + 24bit/48000 formats: both opened [legacy confidence: facts high; cause low-medium; legacy status: open; import... | low | open | V003 |
| F-03 | WASAPI exclusive: recorded 1 kHz loopback tone has dense short noise bursts (87-143/s; 3-9 samples; up to 0.24 FS) [legacy confidence: high; legacy status: open; imported 2026-11-14, capped at low while the instrument is... | low | open | V008,V009 |
| F-04 | WASAPI shared and MME loopback tone clean (error about -62 dB) [legacy confidence: high; legacy status: closed; imported 2026-11-14, capped at low while the instrument is untrusted] | low | closed | V004,V005,V006,V007 |
| F-05 | Fault present at blocks 128 and 256; no late blocks / status flags in exclusive mode [legacy confidence: medium (1 run each); legacy status: open; imported 2026-11-14, capped at low while the instrument is untrusted] | low | open | V008,V009 |
| F-06 | S1: digital silence 0.1 s then decaying start-up thump (peak 0.074), then clean [legacy confidence: high (exists); device unknown; legacy status: open; imported 2026-11-14, capped at low while the instrument is untrusted... | low | open | V001,V002 |
| F-08 | App opens 1 input channel for the stereo Line In [legacy confidence: high; legacy status: open; imported 2026-11-14, capped at low while the instrument is untrusted] | low | open | V011,V012,V013 |
| F-09 | Software candidate (T023): effect tails cut at exact-silence blocks [legacy confidence: medium (synthetic); legacy status: open; imported 2026-11-14, capped at low while the instrument is untrusted] | low | open |  |
| F-10 | Mode-dependent fault; attribution hardware/driver/software not yet possible [legacy confidence: n/a; legacy status: open; imported 2026-11-14, capped at low while the instrument is untrusted] | low | open | V008,V009,V011,V012 |
| F-11 | Lab captures 14:42-14:45: output.wav (engine output buffer) is a perfect 0.3 sine in excl128, excl256 and shared256; raw.wav is damaged only in excl256 (-10.2 dB; 1382 bursts; 72.7/s; median gap 9.0 ms; width about 19 sa... | low | closed | V011,V012,V013 |
| F-12 | Exclusive 128 was clean in session 2 (-60.7 dB, 0 bursts) but bad in session 1 (143 bursts/s): the fault is intermittent; exclusive 256 bad both times [legacy confidence: medium (1 run per cell); legacy status: open; imp... | low | open | V008,V009,V011,V012 |
| F-13 | Bursts are not tied to the block (start offset spread over all eighths of the 256 block) and evenly spaced in time (about 9 ms); callback 0.09-0.45 ms; no status flags [legacy confidence: high; legacy status: closed; imp... | low | closed | V012 |
| F-14 | Owner-reported device list: webcam microphone offers WASAPI 16000 Hz only, Realtek Line In 48000 Hz; S1 -9997 'Invalid sample rate' most likely came from the webcam as default input (supersedes the F-02 cause 'low-medium... | low | open | V014,V003 |
| F-16 | WASAPI exclusive 48000/128 mounted fine at 14:40:04 on Line In + Speakers; ASIO4ALL v2 installed but untested; the tools have no ASIO entry [legacy confidence: medium; legacy status: open; imported 2026-11-14, capped at ... | low | open | V014 |
| F-17 | Correction to F-16: ASIO4ALL v2 is in the app device list (ID 10, In 2 Out 8) and main.py enables ASIO; only the matrix tool has no ASIO key [legacy confidence: high; legacy status: open; imported 2026-11-14, capped at l... | low | open | V014 |
| F-18 | Late-block warnings in the log (worst 447 %) appear 5-6 s after each capture stopped = while ANALYZE ran; captures themselves have 0 late blocks [legacy confidence: medium-high (timing match; not tested by unmounting fir... | low | open | V014,V011,V012,V013 |
| F-19 | Possible factor: excl128 captured 2 min after mount (clean); excl256 captured 7 s after a fresh mount (bad); the fault looks constant within a capture [legacy confidence: low (3 data points); legacy status: open; importe... | low | open | V011,V012,V014 |
| F-21 | In E003 excl256 (V012) all 1382 burst starts lie on one phase of a 144-sample (3.000 ms) grid: maximum deviation 0 samples, every gap between starts is a multiple of 3 ms (3 to 87 ms, mean 13.7 ms), phase concentration R... | low | open | V012,V008,V009 |
| F-22 | The imported evidence contains no round-trip latency measurement for any path; the only latency figure is the app's own log text for shared mode (about 37 ms). Stage 1 (lowest real latency) therefore has no evidence. An ... | low | open | V014,V010 |
| F-23 | Replay: the legacy tone-residual numbers (err_db, bursts, bursts/s, max residual, median width, median gap) of the three Lab raw.wav captures (V011, V012, V013) were recomputed here from the recordings and match the lega... | low | closed | V011,V012,V013 |

## Hypotheses

| Id | Statement | Status | Confidence | Evidence |
|---|---|---|---|---|
| H001 | The bursts are created in the exclusive-mode path after the engine's output buffer (playback driver / card, analog loop, or exclusive capture), not by the progr... | supported | low | V011,V012,V013 |
| H002 | The bursts come from the program's own stream handling in exclusive mode (PortAudio exclusive format conversion, stream arguments, 1-channel open of a stereo Li... | open | none |  |
| H003 | Exclusive-mode crackle is intermittent and decided by a state that can change between runs (stream open, mount age, device format, driver), so one clean capture... | open | low | V008,V009,V011,V012 |
| H004 | Windows / driver settings of the onboard Realtek (24 bit device format and its conversion, exclusive-priority option, enhancements, Realtek vs Microsoft HD Audi... | open | none |  |
| H005 | Some path on this PC (WASAPI exclusive, ASIO4ALL, WDM-KS) measures a round trip of 20 ms or less at a block size that is also free of crackle; the onboard Realt... | open | none |  |
| H006 | WASAPI shared and MME, the only paths measured clean so far, are slower than 20 ms round trip on this PC (the app text says about 37 ms for shared), so the goal... | open | none |  |
| H007 | The bursts are tied to the device period of the exclusive path: the 3.000 ms (144-sample) burst grid seen in V012 is the driver/device period, and bursts occur ... | open | none |  |
| H008 | In the exclusive-type paths the real round trip falls roughly linearly with the block size down to a floor set by the converters and the driver period, so the l... | open | none |  |

## Figures copied from evidence digests (captions go into SHOWCASE.md)

- figures/V003_01_recording_tab_webcam_default_1421.png
- figures/V003_02_playback_tab_speakers_default_1422.png
- figures/V003_03_recording_tab_line_in_default_1423.png
- figures/V003_04_line_in_listen_tab_unchecked_1423.png
- figures/V003_05_line_in_advanced_2ch_24bit_48000_1424.png
- figures/V003_06_speakers_advanced_24bit_48000_1424.png

## Learning log
- present: entries in section 1: 14
