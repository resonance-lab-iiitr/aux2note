# T019 analyze_audio: one command turns a capture into an analysis pack

```
cd CODE
python3 tools/analyze_audio.py captures/20261111_153000_test          # a T020 capture folder
python3 tools/analyze_audio.py take.wav --block-size 64               # any WAV / FLAC (block size if you know it)
python3 tools/analyze_audio.py --compare raw.wav processed.wav        # DSP-made clicks or input clicks?
```
Options: `-o OUT` output folder (default `<folder>/analysis` or `<file>_analysis`), `--max-mb 20` largest zip,
`--excerpts 10`, `--block-size N`, `--channel 0`, `--offset N` (compare: samples to skip at the start of RAW),
`--source raw|processed`, `--effects on|off`, `--monitoring on|off`, `--silent-input`, `--no-png`.
Telling the tool how the capture was made (effects off, monitoring off, nothing played) sharpens the verdict.

**Attach `analysis_pack.zip` to a Claude chat.** It holds report.md (verdict, evidence, next test; read first), report.json,
events.csv (every click / dropout / clipped run), ms.csv.gz (one row per millisecond), report.png (waveform with events,
spectrogram, where events fall inside the audio block), event_01..10.png (worst events, +/- 20 ms) and excerpts/*.wav
(+/- 1 s, 24-bit). The raw capture itself stays in your capture folder.

If the pack would be bigger than `--max-mb`, ms.csv.gz keeps every 2nd, 5th or 10th row (events are not lost), then audio
excerpts are dropped; report.md says so. Without matplotlib the pictures are skipped (`pip install matplotlib`, dev only).
Without blocks.csv.gz (a plain WAV) the report says late-block correlation was not possible.

Limits: judged from numbers, not from listening; the verdict rules are hypotheses (crackle_core, T018). Tuned on synthetic
signals; real recordings are tested in T024. `example_pack/` is the output for a synthetic 10 s capture with 14 clicks at
block offset 1, each in a late block.
