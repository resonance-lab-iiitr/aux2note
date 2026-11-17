# Research track (for people)

This project has two kinds of work. **Work** builds the product (tasks T###, code in `CODE/`). **Research** answers a question with
measurements before the plan is changed, or after the product exists to make it better. Both live in the same zip, so one zip is the single source of truth.

## When to use research instead of work
- An open question or a suspected architectural change that is too risky to start building (try the direction cheaply first: type *explore*).
- Something misbehaves and the cause is unknown (type *investigate*).
- The product works and should get better: faster, cleaner, cheaper (type *optimize*: measure a baseline, change one thing, measure again).

## How a study runs
1. **R-PLAN**: the question becomes hypotheses (each with a prediction and what would prove it wrong), experiments, and stage gates with pass/fail rules written *before* any test.
2. **R-BUILD**: Claude writes and sandbox-tests the experiment script and a run sheet for you. The measuring tool is checked first (calibration), so a bad tool is not mistaken for a bad device.
3. **You run the experiment** on your PC with the run sheet. The script ends by building one small *result pack* (`rpack.py`): numbers, small files, hashes, machine facts, your notes. Big recordings stay on your PC (listed by hash).
4. **R-ANALYZE**: attach the project zip and the pack(s). Claude files them as evidence, updates each hypothesis (supported / refuted / inconclusive, with a confidence level) and the findings.
5. **R-SYNTH**: at a gate Claude writes the synthesis into the study report, records a decision, and changes the main plan (adds, edits or cancels tasks). Tasks that depend on the answer wait for the gate (`Gate:` line on their card).
6. **R-IMPORT**: brings older, template-less evidence into a study with its provenance marked as retroactive.

## Rules that make results trustworthy
- Pass and fail rules are written before the run and not edited afterwards.
- One variable changes at a time; at least 3 runs per setting before a verdict.
- While the measuring tool is untrusted, every claim is capped at low confidence. Retroactive evidence is capped at medium.
- Negative and inconclusive results are kept. Earlier claims are never rewritten: a `Correction:` line is added.
- Claude cannot hear audio or touch your hardware; it reads the numbers and files you send, and says what it could not verify.

Files: `PROTOCOL.md` (the rules Claude follows), `templates/`, `lib/rpack.py` (runs on your PC), `studies/` (the work), `notes/` (unfolded session notes).

## Learning and showcase (new in v043)
A study is meant to teach you and to be shown, not only to give a verdict.
- `LEARNING_LOG.md`: Claude adds a few plain-language concepts per session, each tied to a real number or event of your study, with a self-check question. You mark "understood" only after answering it in your own words. Wrong beliefs stay in the log (that is the best interview material). Reading-list entries are `unverified` until someone opened the source; Claude never invents references.
- `SHOWCASE.md` + `showcase/FACTS.md` + `showcase/figures/`: the portfolio page. FACTS.md is generated (`python3 tools/research.py showcase S001`) so counts and claims always match the CSVs; SHOWCASE.md is the narrative you edit into your own voice. A claim is never stronger than its finding (low stays low, "inconclusive" is shown as a result).
- `Depth: deep` (STUDY.md) switches on the academic layer: background, statistics plan before the runs, one-factor-at-a-time table, data dictionary, authorship statement (report sections 9 and 10). Say "coursework", "portfolio" or "academic" in your goal line and Claude sets it.
- `Domain:` adds `DOMAIN.md`, the project-specific detail (for sound: definitions and formulas, environment checklist, standard controls and figures, known pitfalls). New domains are added as one file under `templates/domains/`.
