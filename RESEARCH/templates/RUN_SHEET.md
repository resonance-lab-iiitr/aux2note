# Run sheet E### : title

For: the owner, on the real PC. Print or keep open. Estimated time: [N minutes]. Repeats needed: [N].

## Before you start
- [ ] Unzip the project; open a terminal in the project folder.
- [ ] [Hardware / cable / volume / programs to close / power plan, exact]
- [ ] [Settings that must be as in the study's Environment constants]

## Each run (repeat [N] times; change ONLY: [the one variable])
1. [exact step / command]
2. [exact step / command]
3. Build the pack: `python RESEARCH/lib/rpack.py make E### <label> --file <small files> --raw <big files> --metric name=value`
4. Open `notes.txt` inside `results\E###_<label>.zip`, or write your notes in a text file and pass `--notes file.txt`. Fill every line.

## Send back
Attach the latest PROJECT zip and every `results\E###_*.zip`. Paste `Read START_HERE.md in the attached zip and follow it exactly.` (Claude will see the packs and analyse them.)

## If something goes wrong
Stop, do not "fix" it silently. Put the exact error text in notes.txt, say which step, and still send what you have.
