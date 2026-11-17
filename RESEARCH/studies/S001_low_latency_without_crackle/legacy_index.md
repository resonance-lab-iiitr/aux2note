# S001 legacy index (R-IMPORT 2026-11-14)

Source package: `CrackleLab_Evidence_and_Report_v2_2026-11-12.zip` (sessions 1 and 2 of 2026-11-12, tester = project owner, analysis by an earlier Claude chat). Everything below is retroactive evidence: confidence capped at medium by protocol, and at low while the instrument is untrusted.
Not imported: `project_memory/PROJECT_v036.zip` and `evidence/session1_original_files/original_project_zip/PROJECT_v030.zip` (project copies, never evidence); per-run `ms.csv.gz`, `event_*.png`, `report.png`, `excerpts/` (derived files, stay in the evidence zip). Audio (raw.wav, output.wav) and `analysis_pack.zip` are listed by hash in evidence.csv and stay on the owner PC / in the evidence zip.

## Old documents (copied unchanged to `legacy/`)
| Original file | Now | Note |
|---|---|---|
| 00_READ_ME_FIRST.md | legacy/00_READ_ME_FIRST.md | package index |
| 01_REPORT.md (report v2) | legacy/01_REPORT.md | replaces v1 conclusions where they differ (its section 8) |
| 01a_REPORT_session1_ORIGINAL_unchanged.md (report v1) | legacy/01a_REPORT_session1_ORIGINAL_unchanged.md | kept as it was |
| 02_HANDOFF_next_session.md | legacy/02_HANDOFF_next_session.md | refers to PROJECT_v036 and doc lag 3 (out of date: project is v041, STATE says doc lag 2) |
| 03_findings_register.csv | findings F-01..F-20 of this study | wording kept, confidence mapped (see below) |
| 04_RESEARCH_DIRECTION_low_latency.md | legacy/04_RESEARCH_DIRECTION_low_latency.md | old plan; rewritten into H001-H006, stages and RQs (STUDY.md); its 8 steps are not copied, R-PLAN writes experiments |
| 05_CRACKLE_FINDINGS_final.md | legacy/05_CRACKLE_FINDINGS_final.md | the project-side short findings file |

## Evidence files (V ids)
| V | experiment | run | digest folder | stays on the owner PC / in the evidence zip (name:bytes:sha256 prefix) |
|---|---|---|---|---|
| V001 | E001 | S1_mme_48000_128 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V001 | analysis__analysis_pack.zip:1250678:9167363c8491;raw.wav:3763280:f18c092bb117 |
| V002 | E001 | S1_mme_48000_256 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V002 | analysis__analysis_pack.zip:1170577:098e380dd9eb;raw.wav:3763280:1ead3c13840f |
| V003 | E001 | S1_setup_screens_console | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V003 |  |
| V004 | E002 | S3_mme_48000_128 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V004 | analysis__analysis_pack.zip:369726:46b09e25291c;output.wav:7700568:e46f7484d72f;raw.wav:3850320:29046ac6d219 |
| V005 | E002 | S3_mme_48000_256 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V005 | analysis__analysis_pack.zip:402401:94a8fc08e351;output.wav:7700568:336687049007;raw.wav:3850320:8567e8adf878 |
| V006 | E002 | S3_wasapi-shared_48000_128 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V006 | analysis__analysis_pack.zip:877817:3919d5c2fcf0;output.wav:7710808:e5726159f6a3;raw.wav:3855440:8b9d04fb29fa |
| V007 | E002 | S3_wasapi-shared_48000_256 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V007 | analysis__analysis_pack.zip:859686:73c025aaa082;output.wav:7706712:7ad042b19724;raw.wav:3853392:eae1bcb9d984 |
| V008 | E002 | S3_wasapi-excl_48000_128 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V008 | analysis__analysis_pack.zip:3302931:9f03403cbd8e;output.wav:7680088:660710e6d457;raw.wav:3840080:467b41a79a22 |
| V009 | E002 | S3_wasapi-excl_48000_256 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V009 | analysis__analysis_pack.zip:3266659:8daca212aef3;output.wav:7712856:26ee3c7265d6;raw.wav:3856464:8743a64880b8 |
| V010 | E002 | S3_summary_console_analysis | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V010 | analyze_evidence.py:3522:a603cd2def57 |
| V011 | E003 | 20261112_144217_excl128 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V011 | analysis__analysis_pack.zip:669935:9c129e491176;output.wav:7680088:31d3f78f4572;raw.wav:3840080:12035300ec17 |
| V012 | E003 | 20261112_144415_excl256 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V012 | analysis__analysis_pack.zip:4886238:9ede9c4a6dd7;output.wav:7680088:4875de542170;raw.wav:3840080:8fbffccadfc1 |
| V013 | E003 | 20261112_144533_shared256 | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V013 | analysis__analysis_pack.zip:920246:35a255603074;output.wav:7680088:7c61701c426e;raw.wav:3840080:2740a0de2627 |
| V014 | E003 | session2_app_log_and_analysis | RESEARCH/studies/S001_low_latency_without_crackle/evidence/digests/V014 | analyze_lab_captures.py:1914:d5ba5668cdc5 |

Other originals: console outputs 01-03, matrix summaries, six Windows screenshots with DESCRIPTIONS.md (V003, V010); looper.log and console text of session 2, analysis scripts and outputs (V010, V014).

## Mapping of old claims
- Confidence: every legacy finding is `low` in findings.csv because the instrument is untrusted (validate.py rule); the original word is kept inside each finding text as `[legacy confidence: ...]`. Legacy status `tool defect` became `defect` (F-07, F-15, F-20); other statuses unchanged.
- Old plan (direction file steps 1-8) -> RQ1-RQ3, H001-H006 and the stage lines in STUDY.md. Steps 1 (measure latency) and 2-7 (mount repeats, range matrix, Windows variables, ASIO4ALL, WDM-KS / DirectSound, other hardware) are experiments for R-PLAN; none was run.
- Old success rule (tone error better than -55 dB, 0 bursts/s, 3 consecutive 20 s captures, RTT <= 20 ms) was "proposed, to be agreed". The owner's STATE Goal (under 1 % damaged windows, no all-zero blocks, underflows 0) is a different wording; R-PLAN must fix one pre-registered rule.
- Tool defects D-1..D-10 and G-1 -> Threats in STUDY.md.

## Corrections that apply (kept from the old reports, plus new ones)
- Correction (report v2 section 8, kept): v1 said input and output could not be separated; output.wav separates the program's output from the input recording (H001, F-11).
- Correction (report v2, kept): v1 said the fault shows at blocks 128 and 256; in session 2 exclusive 128 was clean (F-12).
- Correction (report v2, kept): "ASIO4ALL cannot be tested" was too broad; only the matrix tool lacks an ASIO key (F-16 / F-17).
- Correction (report v2, kept): the tool verdict text for excl256 says "nothing playing" (D-3) and judges raw.wav without output.wav.
- Correction (report v2, kept): no exclusive range matrix was supplied; it counts as not tested.
- Correction (R-IMPORT 2026-11-14, new): F-13 / report v2 section 4.2 say the bursts are "evenly spaced in time (about 9 ms)". Recomputed from V012 raw.wav: the median gap is 9.0 ms but gaps range from 3 to 87 ms (mean 13.7 ms, p10 3.0, p90 27.0); only 13 % lie between 8 and 10 ms. What does hold: all burst starts are on one phase of a 3.000 ms grid (F-21). "Not tied to the 256-sample block" still holds.
- Correction (R-IMPORT 2026-11-14, new): report v2 section 1 point 6 and the handoff say latency was "not measured by us"; true, and it means stage 1 has no evidence at all (F-22). STATE Known issues carries one owner-reported RTT (19.8-22.2 ms, split mode, exclusive 48000/160) that is not in this package.
- Correction (R-IMPORT 2026-11-14, new): the direction file says WASAPI shared was clean in 3 captures and MME in 2 (5 of 5 together). The package has WASAPI shared 128 and 256 (session 1) plus shared 256 (session 2) = 3, and MME 128 and 256 = 2. Consistent; noted because the matrix tool labels MME rows "MME shared".
- Not corrected, only flagged: the old reports and the handoff describe the owner's copy as v032 and the memory as v036; this session's project zip is v041. The owner has not said which code ran the 2026-11-12 captures beyond "v032 copy".
