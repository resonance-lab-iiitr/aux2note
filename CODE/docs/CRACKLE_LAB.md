# Crackle Lab: find out if the crackle is hardware or software

**Read this first: nothing in the Crackle Lab has run on a real sound card yet.** Everything was tested with
fake audio streams and synthetic sounds. The first real captures are the point of the next step (task T024).
The verdicts are hypotheses made from numbers, not from listening.

## What the lab does
It records the exact signal the sound card delivers (`raw.wav`) plus the timing of every audio block, then
measures clicks, dropouts, clipping, DC offset and hum, and writes a small "analysis pack" that you attach to a
Claude chat. Claude reads the pack and says whether the crackle looks like hardware, driver, scheduling or software.

## Option 1: the Lab tab (inside the app, Ctrl+5)
1. Audio tab: choose your device and MOUNT. The Lab START button stays grey until the engine is mounted.
2. Lab tab: pick a test type, a duration (5-120 s, default 20) and a label, then START CAPTURE.
3. ANALYZE (the new capture is already selected). The verdict, the evidence lines and report.png appear in the tab.
4. OPEN FOLDER shows `analysis/`. The file to attach is `analysis/analysis_pack.zip`.

What each test type needs:

| Test type | What you do | What it tells you |
|---|---|---|
| Silent input | Unplug the input or mute the source. Stay quiet. | Clicks here come from the card, driver or computer, not from the music. |
| Test tone (cable out -> in) | Cable from the output to the input, Windows volume LOW. A 1 kHz tone is played and recorded back. | Whether a clean tone comes back clean. Also saves `output.wav`. |
| Live source | Play music or an instrument into the input. | The real-life case. |
| Playback only | Tone out, input unplugged. | Block timing only (is the app on time?). |

Monitoring is switched off during a capture and put back afterwards.

## Option 2: the matrix (many modes in one go)
Runs the same captures in every driver, mode, sample rate and block size and writes one table.
Run from the CODE folder on the Windows PC:

    run_crackle_matrix.bat --dry-run     (shows the plan and the total time, opens nothing)
    run_crackle_matrix.bat --quick       (about 8 minutes: blocks 128 + 256, 48000 Hz, WASAPI + MME)

You will be asked to change cables at the start of each scenario (unplug input, muted line-in, cable loop,
live source). Full details: `python tools/crackle_matrix.py --help`.

## What to attach to a Claude chat
- From the Lab tab: `analysis/analysis_pack.zip` of the capture(s).
- From the matrix: `matrix_summary.md` (one page), and the `analysis_pack.zip` of the worst S1 and S3 runs.
- Say which test type or scenario it was and what you heard.

## How to read a verdict
`report.md` (inside the pack) starts with **Verdict: <cause> (confidence ...)**, then the evidence lines, then
the next test to run. Causes you may see: `hardware_or_driver_input` (clicks in the raw input, also when nothing is played), `software_scheduling` (clicks at the start of audio blocks or in late blocks), `software_dsp` (clicks made by the effects), `gain_staging` (clipping), `electrical` (hum, DC offset) and `clean` (nothing found). "Other hypotheses" lists weaker candidates. Confidence `high` means several numbers agree,
not that it is certain. A file without `blocks.csv.gz` (a plain WAV) cannot be checked against block timing.

## The software-only baseline (what the DSP does without a sound card)
Test `tests/test_phase10_baseline.py` renders a standard project (3 tracks, every effect on, master FX on) with
no sound card and analyses it. Result (see `DELIVERABLES/T023_crackle_lab_check/baseline_result.json`):
- Effects kept running: 0 clicks, 0 dropouts, 0 clipped runs. The DSP alone is clean.
- **Finding:** if a clip ends in exact digital silence, the track's delay / reverb tail is cut (the effect chain
  is skipped for all-zero blocks), and an effect on the master bus repeats the cut: 7 clicks per channel,
  350 ms apart, in the 3 s after the material ended. This is a software candidate for crackle in loop playback and
  for rendered exports. It is not fixed yet; T024 decides if it matters on real captures.
- Distortion at default settings is normalised to full scale, so a stack of default distortions clips. That is
  gain staging, and the lab reports it as `gain_staging`, not as a click fault.

Sample packs for two synthetic faults (clicks at block starts; DC offset + 50 Hz hum) are in
`DELIVERABLES/T023_crackle_lab_check/`. Open `report.md` in each to see what a pack looks like.
