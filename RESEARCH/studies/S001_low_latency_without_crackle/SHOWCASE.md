# S001 showcase : Low latency without crackle

Status: draft        Last updated: 2026-11-14        Based on evidence up to: V014        Study stage: 0 (legacy evidence imported, no new runs yet)
Rule: every claim below cites a finding or evidence id and carries its confidence word. Nothing here is stronger than findings.csv allows. Claude may write this file; the owner reads it and edits his own voice into it. Run `python3 tools/research.py showcase S###` to refresh the generated FACTS.md and figures next to it.

## One sentence
Can a live audio program on a normal Windows PC reach a 20 ms round trip without crackle? So far: the safe Windows path is clean, the fast path crackles intermittently, the fault lies after the program's own output (low confidence), and nobody has measured the real latency yet.

## The problem (why anyone should care)
A looper used while playing needs very low delay, but the fast Windows audio path (WASAPI exclusive) produced noise bursts in 3 of 4 test captures while the slow paths were clean in 5 of 5. Whether the goal is reachable on this hardware is unknown.

## Approach in five bullets
- Question split into latency (stage 1) and crackle (stage 2); six hypotheses with rivals (H001-H006).
- Instrument: Lab capture chain and detector, untrusted until calibrated; legacy numbers re-derived from raw recordings and matched (F-23).
- Legacy runs imported as retroactive evidence (13 runs / setups, capped at medium, here at low); new runs will be pre-registered with 3 or more repeats and controls.
- Measured so far: tone residual and burst rate of 1 kHz loopback captures, with the program's own output recorded as a control.
- Decisions by stage gates with numeric rules written before the runs (to be written in R-PLAN).

## Headline results (numbers, confidence, ids)
| Claim | Number | n | Confidence | Evidence |
|---|---|---|---|---|
| Slow paths (shared, MME) are clean | tone residual -62.7 to -61.5 dB, 0 bursts | 5 | low (untrusted instrument) | V004-V007, V013 |
| Exclusive path is intermittently damaged | 3 of 4 captures; damaged excl256 -10.2 dB, 72.7 bursts/s | 4 | low | V008, V009, V011, V012 |
| Program output is clean while input is damaged | output -152.5 dB (perfect sine) in all 3 Lab captures | 3 | low | V011-V013 |
| Burst starts sit on a 3.000 ms grid | R = 1.000 (0.027 expected at random), max deviation 0 samples | 1 capture | low; artefact not excluded | V012 |
| Real round-trip latency is unknown | no measurement in the evidence | 0 | n/a | F-22 |

## What a reader can check (reproduction)
`python3 RESEARCH/studies/S001_low_latency_without_crackle/spikes/legacy_replay_burst_grid.py <capture folder>` (needs numpy, soundfile; recordings stay on the owner PC, listed by hash in evidence.csv). Legacy script: `analysis/analyze_lab_captures.py` in the evidence package.

## Who did what (honest authorship)
- Owner: PC, cable, the 2026-11-12 test runs, owner goal, decisions.
- AI assistant (Claude): research structure, analysis scripts, replay, writing. Claude cannot hear audio or touch the PC; all numbers come from files the owner produced.

## Skills demonstrated
Experiment design with rival hypotheses, instrument-trust thinking, signal analysis (sine fit, burst detection, circular statistics), reproducible scripting, honest reporting of limits.

## Limits (say them first when asked)
One PC, one cable, one run per setting, instrument not calibrated, no latency measured, 3 ms grid seen in one capture and possibly a tone artefact, no listening.

## Talking points
- 30 seconds: see learning log section 3.
- 2 minutes: question, rival hypotheses, why one clean run proves little, what the control recording shows, what is still unmeasured.
- The hardest mistake I corrected: "evenly spaced 9 ms bursts" was wrong; the real regularity is a 3.000 ms grid (LEARNING_LOG section 4).

## Figures and files
Generated `showcase/FACTS.md` (counts and claims from the CSVs). Figures: none yet; R-PLAN adds figure scripts under `spikes/`.
