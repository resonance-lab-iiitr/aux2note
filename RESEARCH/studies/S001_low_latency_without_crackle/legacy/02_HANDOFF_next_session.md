# Handoff for the next session (updated 2026-11-12, after sessions 1 and 2)

## State
Project zip: `project_memory/PROJECT_v036.zip` (use this one; v033 and v035 are older). Doc lag 3, so the next Claude session is DOC mode (START_HERE does it automatically). Then a PLAN session for tool defects D-1..D-10 and the low-latency research. T025 (declicker) is a full card; T026, T027 and the audio phase wait.
Findings in one paragraph: the engine's output is clean; the WASAPI exclusive input recording is intermittently damaged (3 of 4 captures); shared and MME are clean (5 of 5). Goal: 10 to 20 ms or lower without crackle (see `04_RESEARCH_DIRECTION_low_latency.md`).

## What to attach to the next chat
1. `PROJECT_v036.zip` and the one-line prompt `Read START_HERE.md in the attached zip and follow it exactly.`
2. Any new captures (raw.wav, output.wav, report.md per capture), latency numbers, `notes.txt`, `looper.log`.
This evidence zip is for reference; the project zip already holds the report and light evidence.

## Owner's next steps
Follow the plan in `04_RESEARCH_DIRECTION_low_latency.md` (steps 1 to 7). Click UNMOUNT before ANALYZE. Use WASAPI shared for normal work until a low-latency mode is proven clean.
Also: check on your PC that the mouse-wheel error is gone in v036 (open a drop-down list, scroll; no CRIT line in the log).

## Do not
- Do not conclude "hardware" from the exclusive result alone: the data supports "after the engine's output buffer", nothing finer.
- Do not accept the S1 verdict as evidence about the Realtek.
- Do not inherit the earlier chat claims listed in report section 8.
