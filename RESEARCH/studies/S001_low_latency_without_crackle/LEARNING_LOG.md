# S001 learning log : Low latency without crackle

Purpose: turn the study into things the owner actually understands and can explain (course work, interviews, a report). Claude writes entries in plain language, at most 5 new entries per research session, each tied to something that really happened in THIS study (cite V / F / E ids). The owner marks "understood" only after the self-check question is answered in his own words.
Rules: no invented references; a source goes into the reading list as `unverified` until someone opened it (web search / fetch or the owner) and the line says what was checked. Wrong beliefs are kept (section 4), never deleted.

## 1. Concepts (plain explanation, where it showed up, self-check)
| Term | Plain explanation (2-3 sentences, with a number from the study if possible) | Seen in (ids) | Self-check question | Understood (no / partly / yes) |
|---|---|---|---|---|
| Block time | The time one buffer of audio lasts: frames / rate. At 48000 Hz a 128-frame block is 2.67 ms and 256 is 5.33 ms, so smaller blocks mean less delay but less time for the computer to deliver the next one. | F-11, V011, V012 | What is the block time of 64 frames at 44100 Hz? | no |
| Round-trip latency (RTT) | The delay from a sample leaving the program to the same sample coming back in through the cable: output buffers + DAC + ADC + input buffers + program buffering. This study has no measured RTT yet (F-22); the only number is the app text, about 37 ms in shared mode. | F-22, V010 | Why is a calculated floor not a measurement? | no |
| WASAPI shared vs exclusive | Shared goes through the Windows mixer (slower, tolerant); exclusive talks to the device directly (can be faster). Here shared and MME were clean in 5 of 5 captures and exclusive was damaged in 3 of 4. | F-03, F-04, V004-V009, V011-V012 | What does the mixer add and why might exclusive be fragile? | no |
| Tone residual (err dB) | Fit one perfect 1 kHz sine to the recording and measure what is left over relative to the tone. About -62 dB is clean here; the damaged exclusive 256 capture was -10.2 dB. | F-23, V011-V013 | Why does a perfect sine give a clean yes / no test for damage? | no |
| Control signal (output.wav) | A second recording of what the program sent out. It was a perfect sine (-152.5 dB) while the input was damaged, so the damage appears after the program's output buffer (H001, low confidence). | F-11, V012 | What does this control NOT rule out (see H002)? | no |
| Instrument trust | A measuring tool must be shown to give the right answer on a known input before its results count. Until then every claim here is capped at low. | STUDY.md Instrument | What would a calibration for the click detector look like? | no |
| Retroactive evidence | Old tests that were not planned with rules in advance. They are useful but never above medium confidence, because the rules could have been chosen after seeing the data. | legacy_index.md | Why does pre-registration protect against fooling yourself? | no |
| Failure bound 3/n | If something failed 0 times in n runs, its failure probability could still be about 3/n (95 %). Ten clean runs only show "under about 30 %". | PROTOCOL rule 5, F-12 | How many clean runs support "under 10 %"? | no |
| Phase concentration R | A number from 0 to 1 showing whether events happen at the same phase of a repeating period. In V012 R = 1.000 for a 144-sample (3.000 ms) period against 0.027 expected by chance. | F-21, V012 | Why must the tone frequency be changed to test whether this is an artefact? | no |
| Delay by cross-correlation (matched filter) | To measure the round trip the tool plays a 30 ms chirp, records what comes back and slides the known chirp along the recording; the position where the match is best is the delay, refined to a fraction of a sample, and a match below 0.35 counts as a missed burst. A chirp spreads its energy over many frequencies, so the peak is sharp even in noise. | E004, F-22 | Why is a chirp easier to locate in noise than one short click of the same height? | no |
| Round-trip model: RTT = intercept + slope x block time | If the round trip is a straight line of the block time, the slope says how many block-lengths of buffering the path adds (in plus out) and the intercept is the fixed part (converters, driver). It predicts what a smaller block should give before it is measured, and a flat line means block size is not the lever. | H008, E008 | If the slope were 3 and the intercept 4 ms, what would a 64-frame block (1.33 ms at 48000 Hz) give? | no |
| Device period versus requested block | A driver may move audio in its own fixed chunks. If the program asks for a block that does not fit those chunks, a layer in between has to re-cut them. V012 shows bursts only on a 3.000 ms (144-sample) grid, which is why blocks 144 and 288 are tested as an idea, not a fact. | H007, F-21, V012 | Why would a 256-frame block and a 144-frame period not line up, and what would line up? | no |
| One factor at a time (ablation) | Change one thing between runs and keep everything else fixed, so a difference can only come from that thing. The legacy run E003 changed mode, block and mount age together, so it could not say which one mattered. | E003, E007, E008 | What could you not conclude from E003 and why does E007 change only the path? | no |
| Margin rule at a threshold | For "reaches 20 ms" a median of 19.9 ms is not enough: runs wobble. The rule asks that every run is at or below 20.0 ms and that mean + 3 x SD is also at or below 20.0 ms, so the line is cleared with room to spare. It is a decision rule, not a proof for all future runs (n = 5 cannot bound a rare bad run). | G002, E006 | A cell has run medians 19.2, 19.4, 19.3, 19.9, 20.4 ms: does it reach the goal, and what do you do next? | no |
| Control run (unplugged cable) | A test where the answer must be "nothing": with the cable out, the sweep should not be heard. If it is heard, the signal went another way; if the run crashes, the control proves nothing. In E006 both unplugged runs crashed (FAILED, not NO SIGNAL). | E006, F-25, V015 | Why is a crashed control not the same as a control that heard nothing? | no |
| Repeatability versus accuracy | Five runs giving 40.74 to 40.93 ms (spread 0.19 ms) show the measurement repeats; they do not show 40.8 ms is the true delay. A wrong but steady instrument is also repeatable (E004 checks accuracy). | F-24, V015 | What would a steady but wrong reading look like? | no |
| Reported versus measured latency | The stream says 49.3 ms (shared) and 112 ms (MME) it will add; the chirp measured 40.8 and 127.5 ms. They differ by -8.5 and +15.5 ms, so the driver's own figure is not a measurement. | F-24, V015 | Why can one number be below and the other above the measured value? | no |
| Device driver (class driver) | Windows can use its own built-in High Definition Audio driver or the maker's (Realtek). Here the Microsoft one is installed (10.0.19041.1). The driver sets the buffer period and which modes exist, so a driver change is a different experiment. | F-27, H004 | Why can results from the old Realtek driver not be reused for this one? | no |
| Reading a preview critically | A script's own summary can be wrong: the E006 preview said "unplugged heard nothing: yes" though both runs crashed, because the test was detected == 0. Check the raw rows. | F-26, V015 | Which column of runs.csv shows the preview was wrong? | no |

## 2. Methods learned (what the technique is, why it was chosen, its limit)
| Method | Why used here | Assumption / limit | Seen in (ids) |
|---|---|---|---|
| Re-analysis from raw recordings | Recompute headline numbers from the files before trusting a report | Reproduces arithmetic only, not correctness | F-23 |
| Circular statistic on event times | Tests for a fixed time grid without choosing a bin size | Can be an artefact of the test signal | F-21, V012 |

## 3. How to explain it
- In 30 seconds (no jargon): My audio program sounds clean when it goes through the safe Windows path but crackles in the fast path. The program's own output is perfect, so the fault is after it; I do not yet know which part, and I have not yet measured how fast the fast path really is. (draft by Claude; owner rewrites)
- In 3 minutes (question, method, result, limit):

## 4. What I believed, what the data said (kept, never deleted)
| Date | Belief before | What the evidence showed | Ids |
|---|---|---|---|
| 2026-11-14 | A report said the crackle bursts are evenly spaced about 9 ms apart | Median gap is 9.0 ms but gaps range 3 to 87 ms; what is regular is a fixed 3.000 ms grid (one capture) | F-13, F-21, V012 |
| 2026-11-14 | Earlier chats treated "exclusive 128 is bad" as settled | Session 2 exclusive 128 was clean; the fault is intermittent (one run per cell proves little) | F-12, V008, V011 |
| 2026-11-14 | Preview said the unplugged control heard nothing, so the set-up looked fine | Both unplugged runs crashed (FAILED, no result); the preview counted detected 0 as silence; the control is inconclusive | F-25, F-26, V015 |
| 2026-11-14 | The card and the old notes assumed a Realtek driver | env_E006.txt shows the Microsoft High Definition Audio driver 10.0.19041.1; no Realtek driver installed now | F-27 |

## 5. Reading list (all `unverified` until opened; say what was checked)
| Topic | Source (author, title, year, link) | Status: unverified / opened / read | What it supports |
|---|---|---|---|
| WASAPI exclusive vs shared and buffer periods | to look up: Microsoft documentation on WASAPI exclusive mode and device periods | unverified | H001 / H002 background |
| PortAudio host API behaviour on Windows | to look up: PortAudio documentation for WASAPI and WDM-KS | unverified | H002 |
| Intermittent-fault statistics (rule of three) | to look up: a statistics reference for the rule of three | unverified | PROTOCOL rule 5 |
| ASIO4ALL buffer and kernel-buffer settings | to look up: the ASIO4ALL manual or help page for its control panel | unverified | E007 / E008 (what the panel value does to the requested block) |
| Time delay estimation by cross-correlation | to look up: a signal processing text or lecture notes on matched filtering and delay estimation | unverified | E004 (how the round trip is read from the recording) |

## 6. Open questions for me (things I still cannot answer)
- Why 3.000 ms? Is it a device period of the driver or an artefact of the 1 kHz tone?
- What is the real round trip of exclusive 128 / 256 on this PC?
- Does ASIO4ALL follow the block the program asks for, or its own panel value (E007)?
- Is the 20 ms line reachable at all on the Realtek card, and with what margin (G002)?
