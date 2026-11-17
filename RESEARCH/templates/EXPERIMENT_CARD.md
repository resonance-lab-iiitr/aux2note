# E### : title

ID: E###
Study: S###
Stage: 0
Kind: measure
Status: planned
Tests: H###
Registered: YYYY-MM-DD
Repeats: 3
Script: RESEARCH/studies/S###_name/scripts/e###_name.py
Outputs: results/E###_<run>.zip
Pass rule: [the exact numbers that count as support, written BEFORE the run]
Fail rule: [the exact numbers that count as refutation, written BEFORE the run]
Changed: [the ONE thing that differs between runs of this experiment]
Held fixed: [everything else that must stay the same]
Controls: [what else is run to show the result is not an artefact: known-good input, minimal script without the app, a second device]
Metrics: [names and units the pack's metrics must contain, e.g. rtt_ms, bursts_per_s, tone_error_db]
Confounds: [what could also explain a result; how this design limits it]
Notes to record: [what the owner must write in notes.txt for this experiment]

<!-- Kind: calibration (checks the instrument) | measure | control | spike (prototype of a direction, code in the study's spikes/ folder) | replay (re-analysis of existing evidence, no owner run).
     Status: planned (card written, script not yet built) | ready (script tested in the sandbox AND a run sheet exists, waiting for the owner) | analyzed | abandoned.
     Pass rule and Fail rule are pre-registered: they may not be edited once Status is `ready`. Change the plan with a new experiment card or a `Correction:` line. -->

## Procedure
[Numbered owner steps, exact commands, in the order to do them. Mirrors the run sheet.]

## Analysis plan
[How the numbers will be read: which comparison, which statistic, how many repeats before a verdict. Decided before the run.]

## Results
[Filled in R-ANALYZE only. One table row per run.]
| run | setting | metrics | verdict (supports / refutes / inconclusive) | evidence id |
|---|---|---|---|---|
