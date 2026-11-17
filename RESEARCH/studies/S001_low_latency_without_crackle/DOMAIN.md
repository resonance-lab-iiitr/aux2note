# Domain annex: audio latency and glitches (copy into a study with `new-study ... --domain audio`)

Project-specific knowledge a study on real-time audio needs. Edit it for the study; everything here is definition or arithmetic, not a measured result. Measured values go into findings.csv with V ids.

## 1. Definitions and arithmetic (check each against the tool that reports it)
- Block time (ms) = block frames / sample rate x 1000. At 48000 Hz: 64 = 1.33, 128 = 2.67, 256 = 5.33 ms.
- Round trip (RTT) = time from a sample leaving the program to the same sample coming back in through the cable. Components: output block(s) in the driver/OS, DAC, ADC, input block(s), program buffering. A floor estimate is not a measurement; only `latency_lab` numbers count.
- Tone residual (err dB): fit one sine (free amplitude, phase, offset) to the recording after 1 s; err = 20 log10(rms residual / tone rms). About -60 dB is clean on this PC; the legacy script is `analysis/analyze_lab_captures.py`.
- Burst: bad samples (residual above 0.02) closer than 20 samples form one burst; bursts per second = count / seconds analysed. Damaged-window share = windows with a burst / all windows (state the window length).
- Failure bound for "never happens": about 3/n at 95 % after n clean runs (n = 10 -> 30 %, n = 30 -> 10 %).
- Burst timing grid: phase concentration R = |mean exp(2 pi i (start mod P) / P)| for period P samples; 1 = all on one phase, about 1/sqrt(n) = random. Use a tone whose period does not divide P, or the grid can be an artefact.

## 2. Environment checklist (record in every pack's notes / STUDY.md, because these changed results elsewhere)
Windows build; audio driver name and VERSION (Realtek or Microsoft HD Audio); device default format (bit depth, rate) for BOTH devices; exclusive-mode options (allow, priority); enhancements; power plan; other audio programs; cable and jacks; Windows volume; sample rate and block of the run; app / code version; mount age (seconds since mount) at capture.

## 3. Standard controls
Known-good path (shared or MME at the same cable); output.wav beside raw.wav; synthetic signal with injected bursts through the detector (calibration); a minimal PortAudio script without the app (program vs device); a second device if one exists; digital silence is a poor test for click detectors (false clicks).

## 4. Standard figures (generate from evidence, caption with ids)
Waveform and spectrogram of one burst; bursts per second per setting with n; RTT per path with min / median / max; timeline of one capture (burst starts); gap histogram. Figures are made by scripts kept in the study's `spikes/`, never edited by hand.

## 5. Glossary seeds for the learning log
WASAPI shared vs exclusive, MME, DirectSound, WDM-KS, ASIO, PortAudio callback, xrun / underflow / overflow, sample rate, bit depth, buffer / block / period, DAC / ADC, loopback, residual, spectrogram, effect tail, dither.

## 6. Pitfalls already met in this project
Analysis running while the engine is mounted disturbs the audio; one clean run of an intermittent fault proves little; tool verdict text is a hypothesis; a webcam microphone can silently be the default input; summing two changes in one run (mode and block) confounds the result.
