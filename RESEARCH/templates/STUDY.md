# S### : title

ID: S###
Title: short title
Type: investigate
Status: planning
Stage: 0
Instrument trust: untrusted
Baseline: none
Depth: standard
Domain: none
Created: YYYY-MM-DD

<!-- Depth: standard | deep (deep adds the academic layer of PROTOCOL rule 13: background, statistics plan, ablations, data dictionary). Domain: none | audio (copies templates/domains/<name>.md into the study as DOMAIN.md).
     Type: investigate (find a cause) | explore (try an architectural direction, end with go / no-go) | optimize (baseline vs candidate).
     Status: planning | running | paused | closed.   Instrument trust: untrusted | trusted | n/a.
     Instrument trust is `untrusted` until a calibration / control experiment shows the measuring tool gives the right answer on a known input.
     While untrusted, every hypothesis and finding is capped at confidence `low` (validate.py enforces this).
     Baseline: optimize studies only; the experiment id that measures the starting point (E###). Others: none. -->

## Research questions
RQ1: [one question that can be answered with measurements]

## Why it matters (link to the main plan)
[Which tasks / phases wait for the answer. What changes in the plan if the answer is yes, and if it is no. Put a `Gate: G###` line on those task cards.]

## Stages
[One line per stage: what it settles, its gate id (rows live in gates.csv).]
- Stage 0: trust the instrument (calibration / control). Gate G###.
- Stage 1: ...

## Instrument
[What produces the numbers. Known defects. How it was validated (known-good input, control run). What would make it untrusted again.]

## Environment constants
[Held fixed for the whole study: machine, device, cable, OS settings, versions. Anything that changes goes into the experiment's "Changed" line.]

## Threats to validity
[Running list: confounds, small n, tool defects, things nobody has controlled. Add, never delete (strike through with `Resolved:`).]
