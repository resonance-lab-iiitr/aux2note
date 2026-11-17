# S001 study report : Low latency without crackle

Status: [draft | gate G### decided | closed]   Last synthesised: YYYY-MM-DD   Based on evidence up to: V###

## 1. Question and why it matters
[RQs, the plan items waiting for the answer.]

## 2. Method
- Instrument and its validation (what was checked, result):
- Environment (machine, device, OS settings, versions; from env.json of the packs):
- Procedure in one paragraph; link to the experiment cards.
- Pre-registered rules (Pass / Fail rules, repeats) and any deviation, stated honestly.

## 3. Results
[One table per question: setting, n, metric mean / min / max, verdict. Numbers only; every row cites an evidence id.]

## 4. Analysis
[What the results show, what they do NOT show, alternative explanations still open. Confidence per claim (see PROTOCOL).]

## 5. Threats to validity and limitations
[Small n, tool defects, uncontrolled factors, things Claude cannot verify.]

## 6. Decision and impact on the main plan
[Gate, outcome, decision id (D###), tasks added / changed / cancelled, ROADMAP change.]

## 7. Reproduction
[Exact commands, script versions, pack names and hashes, how to re-run.]

## 8. Corrections
[Only `Correction:` lines. Earlier text stays.]

## 9. Background and methods (academic layer; Depth: deep; written by R-PLAN 2026-11-14, before any new run)
- Background: see STUDY.md "Background" and LEARNING_LOG.md section 1 (block time, round trip, WASAPI shared vs exclusive, cross-correlation delay, RTT line, device period vs block, one factor at a time, margin rule). Sources: none opened yet; the reading list (LEARNING_LOG section 5) holds topics to look up, all `unverified`.
- Statistics plan: fixed in STUDY.md "Statistics plan" (unit = one run; latency decision by a margin rule, all 5 run medians at or below 20.0 ms and mean + 3 x max(SD, 0.05 ms) at or below 20.0 ms; OLS slope with a 95 % t interval over run medians; crackle tiers 3 of 3 and 30 of 30 with the 3/n bound).
- Ablations: STUDY.md "Ablation table" (E006 repeat, E007 path, E008 block; stage 2 candidates listed, not carded).
- Data dictionary: STUDY.md "Data dictionary".
- Authorship: STUDY.md "Authorship statement" (owner: PC, runs, decisions; assistant: design, rules, scripts, analysis; no listening, no hardware access).

## 10. What was learned
Link: LEARNING_LOG.md (nothing marked understood yet). Corrected beliefs so far (section 4 there): "bursts are evenly spaced 9 ms" became "a fixed 3.000 ms grid in one capture"; "exclusive 128 is bad" became "intermittent". The newest lesson from planning: no latency number exists at all, so stage 1 starts from zero, and the 20 ms line must be judged with a margin rule, not a median.
