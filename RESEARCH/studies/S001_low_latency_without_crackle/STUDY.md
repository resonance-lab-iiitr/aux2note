# S001 : Low latency without crackle

ID: S001
Title: Low latency without crackle
Type: investigate
Status: planning
Stage: 0
Instrument trust: untrusted
Baseline: none
Depth: deep
Domain: audio
Created: 2026-11-14

<!-- Type: investigate (find a cause) | explore (try an architectural direction, end with go / no-go) | optimize (baseline vs candidate).
     Status: planning | running | paused | closed.   Instrument trust: untrusted | trusted | n/a.
     Instrument trust is `untrusted` until a calibration / control experiment shows the measuring tool gives the right answer on a known input.
     While untrusted, every hypothesis and finding is capped at confidence `low` (validate.py enforces this).
     Baseline: optimize studies only; the experiment id that measures the starting point (E###). Others: none. -->

## Research questions
RQ1 (stage 1): What is the lowest real, measured round-trip latency of each audio path on this PC (WASAPI shared, MME, WASAPI exclusive, ASIO4ALL, WDM-KS, DirectSound), and does any path reach 20 ms or less? Nobody has measured it: the only number in the evidence is the app's own text for shared mode (about 37 ms).
RQ2 (stage 2): Where in the exclusive-mode path do the noise bursts come from (playback driver / card, analog loop, capture, PortAudio conversion, program stream handling), and what decides whether a capture is clean or damaged?
RQ3 (join of 1 and 2): Is there a setting that gives 20 ms or less AND clean audio, in enough clean runs to be believed (about 3/n failure bound, protocol rule 5), or does the goal need other hardware?

Owner success criterion (STATE Goal, 2026-11-12, copied; the exact pass rules are fixed by R-PLAN before any run): RTT <= 20 ms in 3 calibrations and 3 clean 20 s Lab tone captures (under 1 % damaged windows, no all-zero blocks, underflows 0). Shared mode stays the safe default until then.

## Why it matters (link to the main plan)
- Phase 12 "audio finish" (T002-T007) and the owner's goal of low-latency, crackle-free audio wait for the answer. Yes (some setting meets both): make that setting the default in the app. No (only shared / MME clean): keep shared as default and the goal needs other hardware (e.g. a USB interface), or program-side work only if H002 is supported.
- T031 (split in/out mode) stays open with its own resume point; it is not part of this study, but its owner-reported figures (see Environment constants) belong to RQ1.
- Phase 10b (tool defects D-1..D-10): the verdicts of the Lab tool are only trusted after Stage 0; R-PLAN decides which defects must be fixed first. T025 (declicker) repairs recordings; it is not a cure for exclusive mode.
- Gate lines (R-PLAN 2026-11-14): T007 (Phase 12 audio check, rc11 release notes and the documented default audio setting) now carries `Gate: G003`: it waits for the answer on which setting is the default. No other card waits: T025 to T027 (offline cleanup) repair recordings and do not depend on exclusive mode; T031 keeps its own resume point (an owner capture with the diagnostic columns) and its RTT figures feed RQ1 only as owner-reported context; Phase 10b tool-defect fixes (D-1 to D-10) are decided by R-SYNTH after G001 (a failed calibration adds the fix tasks that matter first).
- What changes: G002 pass or fail decides whether the default stays shared (and the goal needs other hardware or a driver) or a faster path becomes the candidate default; G003 decides whether it may become the default at all.

## Stages
Imported legacy evidence is all crackle-side and sits at stage 2 (retroactive). Gates and cards written by R-PLAN 2026-11-14 (rules in gates.csv, cards in experiments/).
- Stage 0: trust the instruments. Gate G001. Cards: E004 (latency analyser on known delays, sandbox), E005 (crackle detector on injected bursts, sandbox), E006 (latency repeatability and unplugged-cable control on shared and MME, owner, about 5 minutes).
- Stage 1: lowest real latency per path (H005, H006, H008). Gate G002. Cards: E007 (round trip per path at block 256), E008 (round trip versus block size, paths chosen by E007). Stage 1 is the owner's first goal; the cards are written now because the owner runs are short and the sandbox calibrations need no owner time.
- Stage 2: remove the crackle at the fastest path found (H001 to H004, H007), then join with stage 1 (RQ3). Gate G003 (rule written, no cards yet: candidate cards after G002 are one-factor sweeps in this order: block as a whole multiple of the 3 ms grid H007; a minimal PortAudio script without the app H002; Windows and driver settings H004; Realtek versus Microsoft HD Audio driver). Stage 2 cards need the chosen path from G002, so they are written by the next R-PLAN, not now.

## Background (Depth: deep; general knowledge, not measured here, sources to be looked up and marked in LEARNING_LOG section 5)
A live looper needs the sound to come back quickly: the round trip is the delay from a sample leaving the program until the same sample is recorded again after the sound card (output buffers, digital to analogue converter, cable, analogue to digital converter, input buffers, the program's own buffering). Windows offers several ways to reach the card. WASAPI shared goes through the Windows mixer, which adds delay and tolerance; WASAPI exclusive talks to the device directly; MME and DirectSound are older layers; WDM-KS is the kernel streaming path; ASIO is the professional driver model, and ASIO4ALL is a generic ASIO driver that sits on top of the Windows drivers for cards that have no ASIO driver of their own. A smaller block (buffer) lowers delay but leaves less time for the computer to deliver the next block, so small blocks risk dropouts; separately, if the driver works in its own fixed period, a requested block that does not fit that period can be re-chunked inside the host layer. Whether the Realtek onboard card on this PC can reach 20 ms round trip with clean audio is unknown: the only owner-reported figure (split in/out mode at exclusive 48000/160, 19.8 to 22.2 ms, STATE Known issues) sits right on the line and is not evidence in this study.

## Statistics plan (Depth: deep; fixed by R-PLAN 2026-11-14, before any new run; replaces the R-IMPORT draft)
- Unit of analysis: one run = one process, one stream open to close, 6 chirps. The run median of its 6 bursts is the latency datum; bursts inside a run are correlated and are never pooled as independent samples. For crackle (stage 2) the unit is one 20 s capture.
- Estimand A (latency, stage 1): per cell (path, block), the typical round trip = median of the 5 run medians, with min and max shown, and its margin to the 20 ms line.
- Estimand B (latency model, H008): slope and intercept of run median versus block time per path, ordinary least squares on run medians, 95 % interval from the t distribution.
- Estimand C (crackle, stage 2): per setting, the probability that a 20 s capture is damaged, and the burst rate of damaged captures.
- n per setting and why: 5 runs per latency cell because the tool's own flags use jitter 2 ms and spread 3 ms, and E006 measures the real spread first; 5 gives the range, an SD with 4 degrees of freedom and a run-to-run check, and costs about 35 s per cell; 3 runs for control cells (the owner's rule counts 3 calibrations); 10 more runs in a borderline cell. A "reaches 20 ms" decision needs all 5 run medians at or below 20.0 ms and mean + 3 x max(SD, 0.05 ms) at or below 20.0 ms, so a cell passes only with a margin that is several run-to-run SDs wide (not a statistical test of a population mean: it is a margin rule, chosen because the question is a threshold, and n = 5 cannot bound a rare outlier run). For crackle: n = 3 clean captures meets the owner's goal and proves almost nothing (3/n bound 100 %); n = 10 gives about 30 %, n = 30 about 10 % (PROTOCOL rule 5). G003 states both tiers.
- Effect size and noise: a difference between two latency cells is reported only if it exceeds twice the larger of the E006 spread and the cell spreads; smaller differences are called noise. A resolution floor of 0.05 ms is used for the SD because the analyser interpolates a fraction of a sample (E004 checks it).
- Multiple comparisons: about 4 paths x 9 blocks cells are described, not tested one by one; the two decisions (G002 goal, H008 slope) are the only inferential statements, each with its own pre-registered rule.
- What is not claimed: nothing about other PCs, other cables, other Windows builds or the app with effects loaded and several tracks (the tool uses no effects).

## Ablation table (one factor per experiment, in order; later rows are candidates, not yet carded)
| Factor | Experiment | Levels | Everything else |
|---|---|---|---|
| repeat (no factor): instrument noise | E006 | 5 runs on shared and MME | fixed |
| audio path (host API / mode) | E007 | exclusive, WDM-KS, DirectSound, ASIO4ALL (+ shared control) | block 256, latency low |
| block size | E008 | 32 to 288 frames (9 levels) | path, latency low |
| latency argument (low, block, high, default) | candidate after G002 | 4 | best path and block |
| burst grid vs block as multiple of the period (H007) | candidate (stage 2) | 128, 144, 256, 288 | exclusive, mount procedure |
| program vs device (H002) | candidate (stage 2) | app vs minimal PortAudio script | same device, API, block |
| Windows / driver settings (H004) | candidate (stage 2) | one setting at a time | exclusive 256 |

## Data dictionary (Depth: deep)
| Metric | Unit | Formula / meaning | Produced by (version) |
|---|---|---|---|
| median_ms (per run) | ms | median of the 6 per-burst delays: (position of the correlation peak minus chirp start) / rate x 1000, sub-sample interpolated; bursts with normalised correlation below 0.35 count as missed | CODE/latency_core.analyze via latency_lab.run_one (code at T031) |
| jitter_range_ms | ms | max minus min of the 6 burst delays in one run | wrapper script (R-BUILD) |
| run_median_spread_ms | ms | max minus min of the run medians of one cell | wrapper / R-ANALYZE |
| reported_ms | ms | PortAudio stream.latency input + output (what the driver claims) | latency_lab.run_one |
| gap_ms | ms | measured minus reported | latency_lab.aggregate |
| xruns | count | callbacks after the second with an input or output under/overflow flag | latency_lab.run_one |
| peak_dbfs, noise_dbfs | dBFS | peak of the received chirp; rms of 0.3 to 0.9 s of the recording | latency_core.analyze |
| block_ms | ms | frames / rate x 1000 | latency_lab |
| err_db | dB | 20 log10(rms residual of a one-sine fit after 1 s / tone rms) | spikes/legacy_replay_burst_grid.py (reproduces analyze_lab_captures.py, F-23) |
| bursts, bursts_per_s | count, 1/s | samples with residual above 0.02 closer than 20 samples form one burst; count / analysed seconds | same |
| damaged-window share | % | windows of 100 ms with at least one burst / all windows (definition fixed here; the app's own window definition is not verified) | to be written in the stage 2 card |
| R_144 | 0 to 1 | circular concentration of burst starts at period 144 samples | spikes/ |
| recall, precision | 0 to 1 | matched injected bursts / injected; matched / detected (E005) | E005 script |

## Authorship statement (Depth: deep)
Owner: the PC, the cable and every measurement run, the goal and the decisions, running the sheets and reporting what he heard and changed. Assistant (Claude): study design, hypotheses, rules written before the runs, scripts, analysis and write-up. Claude cannot hear audio or touch the PC: every number comes from files the owner produced or from synthetic signals made in the sandbox, and synthetic results (E004, E005) are labelled as such.

## Instrument
Two instruments, both from the project code and both `untrusted`:
1. Crackle chain: the Lab tab capture tap (raw.wav = input before CLEAN INPUT, output.wav = engine output buffer, blocks.csv.gz timing) plus `crackle_core` / `crackle_report` (click detector tuned on synthetic signals only) and the matrix tool. Known defects D-1..D-10 (report v2 section 9): false clicks in digital silence, verdict without cross-mode comparison, wrong "nothing playing" text, no device names in matrix meta, inflated clicks/min, unclear ADC-gap meaning, ANALYZE with engine mounted, cosmetic items. The tone-residual numbers (err_db, bursts) come from the small legacy script `analyze_lab_captures.py`, not from the app's detector.
2. Latency: `latency_lab.py` / `latency_core.py`. Never run by this study; no latency number exists in the imported evidence.
Validation so far (before R-PLAN): none that counts as calibration. In this import the legacy tone-residual numbers for the three Lab raw.wav files were recomputed from the recordings with the same method and matched to the decimal (V011-V013, spikes/legacy_replay_burst_grid_output.txt): that shows the arithmetic is reproducible, not that the detector is right. Informal controls inside the data: output.wav is a perfect sine in all three Lab captures (err -152.5 dB), and shared / MME captures are clean (about -62 dB). The instrument becomes `trusted` only when a calibration experiment is analyzed and passes its pre-registered rule.

R-PLAN 2026-11-14, calibration plan (rules in gates.csv G001 and in the cards): E004 checks the latency arithmetic and the Calibrator callback logic on known delays, E005 checks the burst detector and the grid test on injected bursts and on clean tones, E006 checks the loopback set-up on the two paths already known to be clean (repeatability, level, xruns, and an unplugged-cable control that must report NO SIGNAL). Instrument trust becomes `trusted` only when G001 is decided pass. These calibrations are synthetic or on the control paths: they do not prove that the Realtek converters, the drivers or the exclusive path give the same answer as the control paths. Latency measured by `latency_lab` includes everything between the program's output and input (converters included); no independent timing reference exists on this PC, which is listed as a threat.

R-ANALYZE 2026-11-14 (E006, V015): E006 did NOT pass. Plugged runs met their numbers (5 of 5 per path, spread 0.188 ms shared, 0.333 ms MME) but the unplugged-cable control returned FAILED (child process produced no result) in 2 of 2 instead of NO SIGNAL, so the pass rule is not met and the fail rule is not met either: inconclusive on the control (F-25). Instrument trust stays `untrusted`. E004 and E005 are still not run.

## Environment constants
Held fixed in all legacy runs (from report v2 section 2; owner PC at D:\PROJECT_v032\PROJECT\CODE, project code v030/v032, Python 3.10, Windows 10 10.0.19041.1):
- Realtek High Definition Audio onboard (Speakers, Line In); NVIDIA HDMI audio not plugged in; webcam microphone ZQ-1080RL (USB, WASAPI 16000 Hz only); ASIO4ALL v2 installed (app device ID 10, untested).
- One 3.5 mm stereo cable, green jack (line out) to blue jack (line in). Line In and Speakers 24 bit / 48000 Hz, exclusive mode allowed and "Give exclusive mode applications priority" ticked, "Listen to this device" off.
- Test tone 1000 Hz, level 0.3, 20 s, 48000 Hz, 1 input channel opened by the program, effects and monitoring off.
Unknown: Windows volume, Realtek driver version, what else was running, whether crackle was audible, owner notes (notes.txt not supplied).
Owner-reported outside this evidence (STATE "Known issues", no file imported): split in/out mode at WASAPI exclusive 48000/160 mounted with RTT 19.8-22.2 ms. This is the only latency number on file from a real card; it is not part of the imported evidence and is not used for any hypothesis here.

R-PLAN 2026-11-14 additions (code facts, read from CODE/):
- The app passes latency "low" (stream_config.py StreamConfig.latency; audio_engine.py builds the stream with it) and opens 1 input channel, default exclusive True and block 64. `latency_lab.py` opens up to 2 input and 2 output channels and lets --latency pick low, high, default (None) or block; its help text says "'default' reproduces the looper app's current setting", which disagrees with the code (the app uses "low"). All cards here use latency "low" to match the app.
- latency_lab names devices with --in and --out (substring); every card names Line In and Speakers explicitly, never the default input (webcam microphone risk, F-14). WASAPI always produces shared and exclusive cells; the wrapper scripts choose the cells a card needs.
- Each latency run is about 6 to 7 s (1 s lead + 6 chirps 0.7 s apart + 0.8 s tail).

R-ANALYZE 2026-11-14 additions (owner PC, E006 run, V015 and env_E006.txt): the driver in use is Microsoft High Definition Audio Device 10.0.19041.1 (2019-12-06), no Realtek driver is listed; the owner says he switched from a Realtek driver (old version and date not recorded) after unsatisfactory results, so legacy runs E001-E003 may have used another driver (unknown). Correction: the lines above that say Realtek driver describe the onboard codec, not the installed driver. Formats Line In and Speakers 2 ch 24 bit 48000 Hz; exclusive ticked; enhancements off; Listen off; Windows volume 50 %; power plan High performance; Python 3.10.0, numpy 1.26.4, sounddevice 0.5.1; also installed NVIDIA Virtual Audio Device 1.2.41.0 and a USB Audio Device. WDM-KS lists no Line In input, only Microphone (HD Audio Mixed capture) (matters for E007). The MME Line In and Speakers names are cut at 31 characters.

## Threats to validity
- Instrument untrusted (defects D-1..D-10; detector tuned on synthetic signals; no calibration); all confidence is capped at low.
- n = 1 per cell in every legacy experiment; exclusive failures 3 of 4, clean shared / MME 5 of 5; the intermittency (excl 128 bad then clean) means one clean run proves little (3/n bound).
- Legacy experiments change two variables at once (mode and block) and none was pre-registered.
- Input device in session 1 was probably the webcam microphone (F-14, owner-reported, not proven); S1 says nothing about the Realtek.
- output.wav is taken in the engine callback, before PortAudio / driver conversion; the program's side of the exclusive stream is therefore not fully separated (H002 open).
- Recordings are channel 0 only; the program opens 1 channel of a stereo Line In (F-08).
- ANALYZE ran while the engine was mounted (D-8); mount age differed between runs (F-19).
- 3 ms burst grid (F-21) rests on one capture and the 1 kHz tone (3 ms = 3 tone periods); a different tone frequency is needed to rule out a detection artefact.
- No latency measurement exists; nothing here says whether 20 ms is reachable.
- Claude cannot hear audio or touch hardware; all numbers come from files.
- Added by R-PLAN 2026-11-14: (a) no independent timing reference: RTT is measured with the program's own chirp, converters and driver delays included; E004 validates arithmetic only. (b) The loopback could travel by another route (Listen to this device, crosstalk): E006 unplugged control. (c) ASIO4ALL may ignore the requested block (its panel decides). (d) Latency is measured without effects and with 1 to 2 channels; the app with effects and several tracks needs more headroom. (e) Latency and crackle are measured by different tools (latency_lab versus Lab tab); a setting that reaches 20 ms in latency_lab must be re-checked in the Lab tab with the app's own stream (1 input channel) in stage 2. (f) 5 runs per cell cannot bound a rare bad run; stage 2 tiers say so. (g) The calibrations E004 and E005 use synthetic data and cannot show what the hardware path does. (h) E006 pass rule asks a tight spread on one path only because the path's own variation and the instrument noise cannot be separated on a single card. (i) Order, time of day and Windows load can drift: cell order is randomised with a stored seed and control cells repeat across sessions.
- Added by R-ANALYZE 2026-11-14 (E006): (a) the unplugged control failed to run (F-25), so it is unknown whether the cable is the only route of the sweep; (b) the wrapper preview counts a FAILED control as silence (F-26); (c) the installed driver is the Microsoft one, so results do not describe a Realtek driver; (d) within-run range is 0.0 ms in all 10 plugged runs, so the run median is effectively one number per run and E004 must show the analyser is not flat by construction; (e) the child's stderr was not saved.
