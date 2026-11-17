# Crackle Lab: real-PC test report (interim, task T024 partly done)

Project: Live Looper Pro (code at T023, build label rc11 + Phase 10 Crackle Lab; project zip v032)
Tester: the project owner, on their own Windows 10 PC
Analysis: Claude, from the files and pasted output the tester provided
Report date: 2026-11-12 (the PC clock in the screenshots shows 12-11-2026, 14:21 to 14:24)
Status: INTERIM. Only scenarios S1 and S3 were run. The cause of the crackle is not yet decided.

---------------------------------------------------------------------------

## 1. Summary

1. The Crackle Lab tools (matrix tool, capture tap, analysis report) ran on a real sound card for the first time and produced 12 usable captures. The tools work, but several of their verdict texts are misleading (section 8).
2. **The first real fault found: in WASAPI exclusive mode the recorded 1 kHz test tone is full of short noise bursts** (about 90 to 140 per second, each 3 to 9 samples long, up to about a quarter of full scale). The same test in WASAPI shared mode and in MME is clean (tone error about -62 dB, no bursts after the start-up edge).
3. The fault shows at both block sizes tried (128 and 256), and the program reported no late blocks and no PortAudio status flags in exclusive mode. So it is not a simple "program too slow" problem. It is specific to the exclusive-mode path.
4. **Where the fault sits is not yet known.** The matrix records only the input. The played tone passes through the program's engine before the card. The input and the output cannot be separated with the data so far. The next test (section 10, step 1) does that separation.
5. The first silence test (S1) is **not usable as evidence about the sound card**. It most likely recorded the webcam microphone, which was the Windows default input at that time, and its "clicks" are artefacts of the analysis tool (sections 5.1 and 8).
6. Nothing here proves "hardware" or "software" yet. The honest status is: a mode-dependent fault was reproduced; attribution comes next.

---------------------------------------------------------------------------

## 2. Test environment

Known (from files and screenshots):
- Windows 10, version 10.0.19041.1. Project unpacked to `D:\PROJECT_v032\PROJECT\CODE`.
- Sound card: Realtek High Definition Audio (onboard). Also present: NVIDIA HDMI audio (not plugged in), a webcam microphone "ZQ-1080RL HD Camera" (USB).
- Windows recording devices at the time of the first screenshot: Microphone (Realtek) not plugged in; Line In (Realtek) not plugged in; Stereo Mix disabled; webcam microphone = default.
- After the cable was connected: Line In (Realtek) = default. Line In default format 2 channel, 24 bit, 48000 Hz; Speakers default format 24 bit, 48000 Hz; "Allow applications to take exclusive control" and "Give exclusive mode applications priority" ticked on both; "Listen to this device" unchecked on Line In.
- Wiring for S3: one 3.5 mm stereo (aux) cable from the green jack (line out) to the blue jack (line in), as stated by the tester.
- All captures: 48000 Hz, 1 input channel (the program always opens 1 input channel), effects off, monitoring off, 20 s each.

Not known (to confirm with the tester): the exact jack colours of this PC (confirmed only by the tester's statement), the Windows volume level during S3, the Realtek driver version, whether any crackle was audible, other programs running, the Windows format of the default devices BEFORE the screenshots were taken.

---------------------------------------------------------------------------

## 3. Method

- The tester ran the project's own tool `run_crackle_matrix.bat`. For each configuration it opens the sound card, records the exact input for 20 s into `raw.wav` (before any effect), records one timing row per audio block (`blocks.csv.gz`), and then runs `crackle_report` to find clicks, dropouts, clipping, DC, hum and to rank causes.
- Scenarios used (their text comes from the tool): S1 silence (nothing plugged into the input), S3 tone loopback (the program plays a 1 kHz tone, a cable carries it from the output back into the input).
- For this report Claude re-analysed the raw recordings independently of the tool's verdicts: per-second levels, tone fit with a free frequency, count of sharp waveform bumps, zero-run lengths, event times. The script is `analysis/analyze_evidence.py`; its output is `analysis/analysis_output.txt`. Every number in this report can be reproduced from the two matrix zips.
- The tool's thresholds were tuned on synthetic signals only. Its verdicts are hypotheses, not proof.

---------------------------------------------------------------------------

## 4. Chronological log: what was done, what came out, what it meant

| # | What the tester did | Exact command / action | Raw result | Finding at this level |
|---|---|---|---|---|
| 1 | Found the jacks and did the Windows setup (closed other sound apps, set volume low) | n/a | Not documented in detail | Setup details unknown, see section 2 |
| 2 | Install check | `run_crackle_matrix.bat --dry-run` and `--help` | Plan printed: 16 configurations x 5 scenarios x 20 s = 80 runs, about 31 min; help text printed; nothing opened | The tool starts and parses options on this PC (file: console_outputs/01) |
| 3 | First real run, silence | `run_crackle_matrix.bat --quick --scenarios S1 --yes --out captures\matrix_S1`, nothing in the input | 6 configurations. 4 WASAPI runs: `open_failed`, `Invalid sample rate [PaErrorCode -9997]`. 2 MME runs `ok`, 24.49 clicks/min, verdict hardware_or_driver_input (medium and high) | WASAPI did not open at 48000 Hz in this state. MME opened. (console_outputs/02, matrix_S1/) |
| 4 | Sent the S1 files | `matrix_S1.zip`, `matrix_summary.md/csv` | Raw WAVs analysed: first 100 ms digital silence, then a large decaying thump (peak 0.074 of full scale) from about 0.1 to 0.4 s, then clean low noise. All 8 reported clicks are inside the first 0.2 s and are 1 to 2 steps of a 16-bit scale | The "clicks" are artefacts. A real start-up thump exists. The S1 verdict is unreliable (section 5.1) |
| 5 | Screenshot of Windows Sound, Recording and Playback tabs | screenshots 01 and 02 | Default recording device was the webcam microphone; both Realtek inputs "Not plugged in" | S1 most likely recorded the webcam microphone, which also explains the WASAPI failure (likely, not proven) |
| 6 | Connected the aux cable green to blue | physical step | Screenshot 03: Line In (Realtek) became the default device | The input is now the Realtek Line In |
| 7 | Checked Line In and Speakers properties | screenshots 04, 05, 06 | Listen unchecked; both devices 24 bit / 48000 Hz; exclusive mode allowed | Settings are consistent with 48000 Hz WASAPI. These are the conditions for S3 |
| 8 | Second real run, tone loopback | `run_crackle_matrix.bat --quick --scenarios S3 --yes --out captures\matrix_S3` | All 6 runs `ok`: WASAPI exclusive 8796 and 5278 clicks/min; WASAPI shared 8.96 and 8.97; MME 2.99 and 2.99 (console_outputs/03, matrix_S3/) | WASAPI now opened at 48000 Hz. Exclusive mode is far worse than the others |
| 9 | Sent the S3 files | `matrix_S3.zip`, `matrix_summary_1.md/csv` | Raw WAVs analysed (section 5.2) | Exclusive mode: dense noise bursts in the recorded tone. Shared and MME: clean tone |

---------------------------------------------------------------------------

## 5. Detailed results

### 5.1 S1, silence (MME only; device probably the webcam microphone)

| Item | Block 128 | Block 256 |
|---|---|---|
| Tool: clicks per minute / dropouts / late blocks | 24.49 / 4 / 1 | 24.49 / 1 / 0 |
| Tool verdict | hardware_or_driver_input (medium) | hardware_or_driver_input (high) |
| First 100 ms of the file | 77 % exact zeros, level about -100 dBFS | same |
| 100 to 400 ms | rms 0.025, 0.055, 0.019 (x100 ms steps); peak 0.074 | rms 0.024, 0.053, 0.017; peak 0.074 |
| After 0.4 s | steady low noise, rms about 0.0012 to 0.002 (about -58 to -54 dBFS) | same; rms rose to about 0.004 around 9 to 11 s |
| Where the 8 detected clicks are | all in the first 0.2 s (102.6 to 105.6 ms, 18 ms, 1.8 ms) | same times |
| Size of those clicks | at most 0.00005 of full scale (1 to 2 steps of a 16-bit scale, about -87 dBFS) | same |

What it means:
- The capture starts with digital silence, then a start-up thump (peak about -23 dBFS) that dies out within about 0.4 s. This is typical of a device or driver settling when a stream opens.
- The "24.5 clicks per minute" and "hardware_or_driver_input (high)" come from the analysis tool flagging 1-step blips in digital silence. After 0.4 s the capture is clean except for one 9-sample repeat at 14.9 s in the block-256 run.
- The identical event times (103.6 ms in both runs, different block sizes) show the events do not depend on the block size.
- Because the default input was probably the webcam microphone, S1 says nothing reliable about the Realtek card. It must be repeated with Line In as the default input (section 10).

### 5.2 S3, tone loopback (cable green to blue, Line In default, 24 bit / 48000 Hz)

| Mode | Tool clicks/min | Bursts per second after 1 s | Tone error vs ideal sine | Samples with sharp bumps | Late blocks / status flags / ADC-time gaps | Tool verdict |
|---|---|---|---|---|---|---|
| MME shared, 128 | 2.99 | 0 | -62.7 dB | 0 % | 0 / 0 / 0 | electrical (medium) |
| MME shared, 256 | 2.99 | 0 | -62.5 dB | 0 % | 0 / 0 / 0 | electrical (medium) |
| WASAPI shared, 128 | 8.96 | 0 | -62.4 dB | 0 % | 0 / 0 / 233 | hardware_or_driver_input (medium) |
| WASAPI shared, 256 | 8.97 | 0 | -61.7 dB | 0 % | 0 / 0 / 2 | hardware_or_driver_input (medium) |
| **WASAPI exclusive, 128** | **8796** | **143** | **-8.8 dB** | **1.68 %** | 0 / 0 / 5 | hardware_or_driver_input (medium) |
| **WASAPI exclusive, 256** | **5278** | **87** | **-5.2 dB** | **0.99 %** | 0 / 0 / 0 | hardware_or_driver_input (high) |

How to read it:
- "Tone error" is the difference between the recording and the best-fitting 1 kHz sine. About -62 dB is clean. About -5 to -9 dB means the recording is badly damaged.
- The 1 to 3 events in the shared and MME runs sit at the very start of the file, where the tone begins abruptly. They are not faults during playing.
- In exclusive mode the damage is spread evenly over the whole 20 s. Example (block 256, t = 9.007 s): a normal sine suddenly shows about 10 jagged samples with jumps of roughly 0.1 of full scale, then the sine continues normally. Events are 3 to 9 samples wide and up to 0.24 of full scale. Tone peak is 0.155 to 0.161 in exclusive mode against 0.128 in the clean modes (the spikes go above the sine).
- Time before the tone first appears: MME about 0.23 s, WASAPI shared about 0.03 s, exclusive about 0.01 s. This is normal start-up behaviour, not a fault.
- The tone frequency is 1000 Hz within a few hundredths of a Hz in every mode, so there is no sample-rate mismatch.

### 5.3 Windows configuration evidence
See `evidence/screenshots/DESCRIPTIONS.md`. In short: after the cable was connected, Realtek Line In was the default input, formats were 24 bit / 48000 Hz on input and output, exclusive mode allowed, "Listen to this device" off.

---------------------------------------------------------------------------

## 6. Findings register

| ID | Finding | Evidence | Confidence | Status |
|---|---|---|---|---|
| F-01 | The matrix tool, capture tap and analysis report run on the real PC and produce readable packs | 12 captures; dry run; two matrix runs | High | Closed |
| F-02 | In S1, WASAPI exclusive and shared failed with `Invalid sample rate -9997` at 48000 Hz; in S3, after Line In became default with 48000 Hz formats, both opened | console 02 and 03; screenshots 01 to 06 | The facts: high. The cause (webcam input or format): low to medium, not verified | Open |
| F-03 | In WASAPI exclusive mode the recorded loopback tone has dense short noise bursts (87 to 143 per second, 3 to 9 samples, up to 0.24 full scale) | analysis_output.txt; events.csv; waveform check | High (reproduced in both block sizes) | Open: cause unknown |
| F-04 | The same test in WASAPI shared mode and MME is clean (tone error about -62 dB) | analysis_output.txt | High | Closed |
| F-05 | The fault does not depend on block size 128 or 256, and the engine saw no late blocks or status flags in exclusive mode | summary tables | Medium (only 2 sizes, 1 run each) | Needs repeat |
| F-06 | S1 recorded a start-up thump (digital silence for 0.1 s, then a decaying thump, peak 0.074) | analysis_output.txt | High that it exists; unknown whether webcam or Realtek | Open |
| F-07 | The 24.5 clicks/min in S1 are analysis artefacts (1 to 2 step events in digital silence) | events.csv | High | Tool defect D-1 |
| F-08 | The program opens 1 input channel (meta.json channels_in = 1) for Line In (a stereo input) | meta.json of every run | High | Check which channel or mix is recorded |
| F-09 | Software candidate from task T023 (not seen yet on real captures): track effect tails are cut when a block is exact digital silence | tests/test_phase10_baseline.py | Medium | Still to check |
| F-10 | Mode-dependent fault: attribution to hardware, driver or software is NOT yet possible | all of the above | n/a | Next test decides |

---------------------------------------------------------------------------

## 7. Corrections to things said earlier in the chat

These were wrong or too strong. They are corrected here so the next session does not inherit them.
1. **"4 configurations per scenario" in `--quick`:** it is 6 (WASAPI exclusive 128 and 256, WASAPI shared 128 and 256, MME 128 and 256), about 2 min 18 s.
2. **"The recording had 1 input channel, so S1 was the webcam":** wrong reasoning. The program always opens 1 input channel, also for Line In (S3 meta files show 1). The webcam suspicion rests only on the default-device screenshot.
3. **"WASAPI failed because the Realtek formats did not match":** not verified. The default input at that time was probably the webcam. The formats before the screenshots are unknown.
4. **"In exclusive mode the tone is cut to zero for about 1 ms many times a second":** wrong generalisation from the first 15 ms of the file (a start-up artefact). The real pattern is dense short noise bursts through the whole file (section 5.2).
5. **The tool's verdict texts** were not repeated as conclusions here: S1's "high confidence hardware" is an artefact, and the S3 reports say "nothing playing" although a tone was played (D-3).

---------------------------------------------------------------------------

## 8. Defects found in the Crackle Lab tools (backlog for the next planning session)

| ID | Defect | Effect | Suggested fix |
|---|---|---|---|
| D-1 | The click detector counts 1 to 2 step events inside digital silence (lead-in before a start-up thump) | False "clicks per minute", false "high" verdict on S1 | Minimum absolute amplitude (for example above -70 dBFS) and ignore regions of exact zeros and the first few hundred ms |
| D-2 | The verdict is made per capture, without comparing modes | S3 says "hardware_or_driver_input" for exclusive while shared and MME are clean, which points at a mode-specific path | Add a cross-mode comparison section to `matrix_summary.md` |
| D-3 | The evidence line "capture was made with nothing playing" appears for the tone loopback scenario S3 | Misleading text | Use the scenario/meta flags (tone, silent_input) in the text |
| D-4 | The matrix records no input or output device name, default format or output capture | Cannot prove which device was used (webcam or Realtek); cannot separate input from output | Save device names and Windows default formats in meta.json; optionally capture the output |
| D-5 | Cosmetic: duplicate "Input:" line in some reports; "noise floor not meaningful" note when a tone is present; "electrical" verdict for a 50 Hz hum at -89 dBFS | Noise in the verdict | Raise the hum threshold; hide the note for tone captures |
| D-6 | `clicks_per_min` counts every event of one burst separately | One thump looks like 8 clicks | Cluster events within a few ms |
| D-7 | 233 ADC-time gaps in WASAPI shared at block 128 but only 2 at block 256, 0 in exclusive 256 | Unclear meaning | Check how gaps are defined for shared mode |

---------------------------------------------------------------------------

## 9. What is still unknown

1. Whether the noise bursts are made at the OUTPUT (the program's tone and engine, or the driver's playback in exclusive mode), at the INPUT (driver or ADC in exclusive mode), or in the cable path.
2. Whether the effect depends on the block size outside 128 and 256, on the rate (only 48000 Hz was tried), or on the exclusive-mode priority setting.
3. Whether the Realtek card is clean when it records silence or live audio in shared mode (S1, S2, S4, S5 were not run on Line In).
4. Whether the tester hears the crackle in the program in exclusive mode and not in shared mode. This is the most useful question for the owner.
5. Whether the T023 software finding (effect tails cut at exact-silence blocks) appears in real use.

---------------------------------------------------------------------------

## 10. Next direction (in order)

Step 1, the key test (about 15 minutes, tester). Capture the OUTPUT as well as the input in exclusive mode. This separates playback from capture.
- Cable still green to blue, Windows volume low.
- `python main.py`; Audio tab: Realtek device, WASAPI exclusive, 48000 Hz, block 128, MOUNT.
- Lab tab: test type Test tone, 20 s, label `excl128`, START CAPTURE, then ANALYZE. Repeat with block 256, label `excl256`.
- Send `raw.wav`, `output.wav` and `analysis\report.md` from each capture folder.
- Decision rule: if `output.wav` is clean and `raw.wav` has bursts, the fault is in the exclusive input path (driver or card): recommend shared mode or a driver change. If `output.wav` also has bursts, the fault is before the card (the program's exclusive-mode stream or engine): a software investigation in `audio_engine.py` follows.

Step 2, repeatability and range (about 5 minutes). Same cable:
`run_crackle_matrix.bat --scenarios S3 --apis wasapi-excl --rates 44100,48000 --blocks 64,128,256,512 --yes --out captures\matrix_S3_excl_full`
Check whether any block size or rate is clean, and whether the result repeats.

Step 3, Windows and driver variables (one change at a time, re-run S3 exclusive after each): untick "Give exclusive mode applications priority"; turn off Realtek audio enhancements; note the Realtek driver version and try the Microsoft "High Definition Audio Device" driver (Update driver, Browse, Let me pick).

Step 4, other devices if available (a USB headset or audio interface) to see whether the exclusive-mode fault is specific to the Realtek.

Step 5, finish the scenarios on the correct input with Line In as the default (needs a cable plugged into the blue jack, so Windows keeps Line In active): S2 (muted source), S4 (live source), S5 (tone, input ignored), and a proper S1 (cable in the blue jack, other end unconnected).

Step 6 (Claude, planning session): turn defects D-1 to D-7 into task cards and fix D-1, D-3, D-4 first, so the next verdicts can be trusted.

Step 7 (owner): note whether the crackle is heard in the program in exclusive mode versus shared mode, and at which block size.

---------------------------------------------------------------------------

## 11. Limits of this report
- Two scenarios only (S1, S3), one run per configuration, one PC, one cable. Repeatability is not yet shown.
- Tool verdicts are hypotheses; the numbers in this report are from independent re-analysis of the raw files.
- The recordings are mono (channel 0). The meaning of the 1-channel input for a stereo Line In is not checked.
- Nothing was listened to; all conclusions are from numbers.

---------------------------------------------------------------------------

## Appendix A: files in this package
See `00_READ_ME_FIRST.md`.

## Appendix B: re-running the numbers
`python analysis/analyze_evidence.py evidence/matrix_S1/matrix_S1.zip evidence/matrix_S3/matrix_S3.zip` (needs numpy, soundfile).
