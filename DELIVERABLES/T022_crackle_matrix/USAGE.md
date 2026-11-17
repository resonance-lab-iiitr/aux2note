# Crackle matrix (T022)

Runs the same captures in every driver, mode, sample rate and block size and writes one table.
Needs the real sound card: run it on your Windows PC from the CODE folder.

    run_crackle_matrix.bat --dry-run                 plan + total time, opens nothing
    run_crackle_matrix.bat --quick                   blocks 128 + 256, 48000 Hz, WASAPI + MME
    run_crackle_matrix.bat --scenarios S1,S3 --seconds 20
    run_crackle_matrix.bat --apis wasapi-excl,mme --rates 48000 --blocks 128,256

Options: `--seconds` (20), `--scenarios`, `--out`, `--rates`, `--blocks`, `--apis`
(wasapi-excl, wasapi-shared, mme, directsound, wdmks, or wasapi for both), `--quick`, `--yes`
(skip the 5 s wait before each scenario), `--dry-run`.

## Scenarios (effects off, monitoring off; raw.wav is the exact card input)
| | what you do | app does |
|-|-|-|
| S1 | unplug the input, stay quiet | nothing |
| S2 | source on line-in, volume at ZERO | nothing |
| S3 | cable output -> input, Windows volume LOW | plays a 1 kHz tone (0.3) |
| S4 | play music / instrument into the input | nothing |
| S5 | as S3 but unplug the input cable | plays the same tone |

Runs are ordered scenario first, configuration second: you change cables at most 5 times.
Default plan: WASAPI exclusive at 64/128/256/512, WASAPI shared, MME, DirectSound, WDM-KS (only
if your PC lists it), each at 44100 and 48000 Hz (14 configurations without WDM-KS; 70 runs of
about 23 s = about 28 min). Use `--quick` for about 8 min.

## Results
`captures/matrix_<time>/` next to main.py: one capture folder per run (`S3_mme_48000_256`),
`matrix_summary.md` (one page: per scenario the lowest clicks/min first, lowest marked *) and
`matrix_summary.csv` (every run: scenario, api, mode, rate, block, seconds, status, clicks_per_min,
dropouts, clipping, xruns, cb_ms_p99, verdict, folder).

status: `ok`; `open_failed` (driver would not open, the error text is in `verdict`);
`fell_back` (the engine's fallback ladder opened a different mode, so no capture was made);
`run_failed`. Ctrl+C stops early and still writes the summary of the finished runs.

## Next
Attach `matrix_summary.md` and the worst S3 / S1 folders (or their analysis packs) to a Claude chat
in task T024. Real-card behaviour (which drivers open, PortAudio status flags) is only known after that.
