# Why is my piano late? Measuring audio latency on a normal Windows PC

*Draft for Dev.to / Medium. Add your own photos where marked. About 900 words.*

**[PHOTO: piano + PC + cable setup, jacks visible]**

I'm a CSE student at IIIT Raichur. In my first-year holidays I had a simple idea: I own a Casio CTK-2500, which has an aux output but no MIDI. Could I do live looping and play other instruments' sounds using only my PC and software, with no audio interface?

## Day one: the sound arrives late

I plugged the piano into the blue line-in jack and the speakers into the green jack. When I pressed a key, I heard it very late, around 150–200 ms by feel. I couldn't play a section in time. Looking it up, I learned that normal Windows audio is built for reliability, not for low delay.

## Trying faster drivers

I installed WASAPI, ASIO4ALL and others. The delay dropped, but the sound had crackles and glitches. A smaller buffer means less time for the computer to deliver each block of audio, so a small buffer can break. Latency and crackle turned out to be one trade-off, not two problems.

## Measuring instead of guessing

I stopped guessing and built a measurement. The software plays a short chirp from the green jack. A cable brings it into the blue jack. The software finds the chirp in the recording and measures the delay. No extra hardware needed.

**[FIGURE: fig4_test_setup.png]**

Results on my PC (block 256, 48 kHz):

**[FIGURE: fig1_latency_by_path.png]**

- **MME: 127.5 ms.** This matches the lag I felt on day one.
- **WASAPI shared: 40.8 ms.** Clean sound, but too slow to play on.
- **WASAPI exclusive: about 20 ms** (reported from earlier runs, not re-measured yet), but it crackled in 3 of 4 captures.

## Finding where the crackle comes from

I recorded a 1 kHz tone through the loop in each mode.

**[FIGURE: fig2_click_timeline.png]**

Shared mode is clean. Exclusive mode shows about 2,000 clicks in 20 seconds. The important check: the signal my program hands to the audio system was a perfect sine wave in every capture. So the damage happens *after* my program, in the driver, the sound card or the capture. That ruled out my own code, which was a relief.

**[FIGURE: fig3_three_ms_grid.png]**

The clicks also line up on a 3 ms grid, which hints that the driver processes audio in fixed 3 ms periods. I only have one capture of this, and a 1 kHz tone could cause the pattern by itself, so I treat it as a lead, not a result.

## What I haven't proven

- My measuring tools aren't calibrated yet, so all findings are low-confidence.
- The unplugged-cable control test crashed instead of reporting "no signal".
- Exclusive mode and ASIO4ALL still need the same formal measurement.

## Where this goes next

Once the delay is low and clean, the real plan starts: detect which notes I play from the audio (constant-Q transform or NMF with per-note templates), turn them into MIDI-like events, and play them through instruments my Casio doesn't have. Later, the same system could transcribe songs with ML models.

## A note on how I worked

I used Claude, an AI assistant, for study design, analysis scripts and much of the code. I ran every measurement on my own PC and made the decisions. Everything is on GitHub: https://github.com/resonance-lab-iiitr/aux2note.

*What would you try next? Suggestions welcome.*
