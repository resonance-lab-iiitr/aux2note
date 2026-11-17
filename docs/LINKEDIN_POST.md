# LinkedIn post draft (attach: fig1, fig2, fig4, plus a short video of you playing)

My Casio piano has no MIDI. Could I loop and re-voice it with only my PC and software?

First attempt: press a key, hear it 150–200 ms later. Impossible to play in time.

So I stopped guessing and measured. A chirp out of the green jack, a cable into the blue jack, and my software times the return.

On my PC (one Windows machine, block 256):
• MME: 127.5 ms
• WASAPI shared: 40.8 ms
• WASAPI exclusive: about 20 ms, but it crackles in 3 of 4 captures

The part I like most: the program's own output was a perfect sine wave in every capture, so the noise enters after my code, in the driver or card. And the clicks line up on a 3 ms grid.

What's not done: my measuring tools aren't calibrated yet, so I call these findings low-confidence. Next: calibrate, test ASIO4ALL, then audio-to-MIDI.

Built as a CSE student at IIIT Raichur with AI assistance (Claude) for analysis and code; every measurement is from my own PC.

Code, data and full write-up: https://github.com/resonance-lab-iiitr/aux2note
Blog: [link]

#AudioDSP #SignalProcessing #Python #Latency #StudentProject
