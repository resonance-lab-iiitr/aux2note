# Handoff for the next session (written 2026-11-12)

## State in one paragraph
Phase 10 (Crackle Lab). Tools T018-T023 and T028 are done. Task T024 (findings from real captures) is PARTLY done: S1 and S3 were run on the owner's PC. A mode-dependent fault was reproduced (WASAPI exclusive: dense noise bursts in the loopback tone; WASAPI shared and MME clean). Cause not attributed. The next evidence needed is a capture of the OUTPUT too (Lab tab, test tone, exclusive 128 and 256).

## What to attach to the next chat
1. `PROJECT_v033.zip` (the project memory; it holds the same report and the lighter evidence).
2. The new captures (see "Owner's next steps"): for each Lab capture the files `raw.wav`, `output.wav`, `analysis\report.md`; plus any new `matrix_summary.md/csv`.
3. A short `notes.txt` (see below).
Then paste the same one-line prompt: `Read START_HERE.md in the attached zip and follow it exactly.`
(The evidence zip you are reading is for you and for reference; the next session does not need it if PROJECT_v033.zip is attached.)

## Owner's next steps (in this order)
1. Cable green to blue, Windows volume low, Line In default (see the report, section 2). Close other sound apps.
2. `python main.py`. Audio tab: driver Windows WASAPI, mode Exclusive, rate 48000, block 128, input Line In and output Speakers (Realtek), MOUNT. Lab tab: Test tone, 20 s, label `excl128`, START CAPTURE, ANALYZE. Repeat with block 256 (`excl256`). Then once more with mode Shared, block 256 (`shared256`) as a comparison.
3. Repeat the quick S3 once and the exclusive range test:
   `run_crackle_matrix.bat --scenarios S3 --apis wasapi-excl --rates 44100,48000 --blocks 64,128,256,512 --yes --out captures\matrix_S3_excl_full`
4. Write `notes.txt`: jack colours used, Windows volume %, Realtek driver version (Device Manager > Sound > Realtek High Definition Audio > Driver tab), what you heard (crackle in the program in exclusive mode vs shared?), what failed to open, any error text word for word.
5. Optional, one change at a time with S3 exclusive re-run after each: untick "Give exclusive mode applications priority"; turn off Realtek enhancements; Microsoft "High Definition Audio Device" driver.

## What Claude should do next (RESUME T024)
- Read `DELIVERABLES/T024_findings/01_REPORT.md` and `03_findings_register.csv` first; do not re-derive the numbers.
- Apply the decision rule: output.wav clean and raw.wav noisy in exclusive => fault in the exclusive input path (driver / card) => recommend shared mode or a driver change, then plan Phase 11. output.wav also noisy => software investigation of the exclusive stream path in audio_engine.py (stream open args, sample format conversion, the tone track mix) with a new task card.
- Write `CODE/docs/CRACKLE_FINDINGS.md` as a final version (tables per scenario; mark what was not tested).
- Plan the tool fixes D-1, D-3, D-4 (and D-2, D-5, D-6, D-7) as task cards before relying on tool verdicts again (needs a PLAN or DETAIL session).
- Keep the corrections in report section 7 in mind (earlier chat claims that were wrong).

## Do not
- Do not accept the S1 verdict ("hardware_or_driver_input high") as evidence about the Realtek card.
- Do not conclude "hardware" from the exclusive-mode result alone: the program's own engine is in the output path of S3.
