# Crackle Lab evidence and report, v2 (2026-11-12): sessions 1 and 2

This package replaces the first one. It contains the old evidence unchanged plus everything added later.

Read in this order:
1. `01_REPORT.md`: full report v2 (goal, environment, chronology, results, log analysis, hardware vs software, corrections, defects, unknowns).
2. `04_RESEARCH_DIRECTION_low_latency.md`: the goal (10 to 20 ms or lower, no crackle), what is known per driver path, the test plan and success rule.
3. `02_HANDOFF_next_session.md`: what to attach and do next.
4. `03_findings_register.csv` (F-01..F-20) and `05_CRACKLE_FINDINGS_final.md` (the short findings file that lives in the project).
5. `01a_REPORT_session1_ORIGINAL_unchanged.md`: report v1, kept as it was.

Contents:
- `evidence/session1_original_files/`: console outputs, Windows screenshots, matrix S1 and S3 (summaries and zips with every raw recording), the project zip v030 the work started from.
- `evidence/session2_lab_captures/`: the three Lab captures of 14:42 to 14:45 (excl128, excl256, shared256), each with raw.wav, output.wav, blocks.csv.gz, meta.json and the analysis folder (report.md/json/png, events.csv, ms.csv.gz, excerpts, analysis_pack.zip).
- `logs/looper_2026-11-12.log`: the app log of the whole session 2 (device inventory, mounts, captures, the wheel error, late-block warnings). `logs/console_after_run.txt`: the console window text.
- `analysis/`: `analyze_evidence.py` + output (session 1), `analyze_lab_captures.py` + output (session 2; needs numpy and soundfile).
- `project_memory/PROJECT_v036.zip`: the current project memory (mouse-wheel bug fixed, 520 tests OK, T024 final findings, T029 done, T025 detailed).

Headline: the program's own output is clean in every capture; the WASAPI exclusive recording has short noise bursts (about 70 to 140 per second when bad, intermittent); WASAPI shared and MME are clean but slow. The fault is after the engine's output buffer; the exact part is not known. Not found: any proof of "hardware" or "software" beyond that.
