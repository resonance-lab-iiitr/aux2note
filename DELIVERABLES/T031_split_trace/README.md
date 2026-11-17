# T031: what the split-stream trace shows (owner files: 2026-11-12 22:43 and 22:45, block 160 @ 48000, prefill 1)

Re-run the numbers yourself: `python tools/split_replay.py logs/split_timing_XXXX.csv` (in CODE/).

## Facts from the csv (no guessing)
| | input stream | output stream |
|---|---|---|
| callbacks per second | 434-444 | 300.1 (correct for 160 @ 48 kHz) |
| frames per second (160 each) | **about 70 000** | 48 012 |
| arrival pattern | bursts every 6.000 ms, 2-4 blocks per burst (avg 2.67) | bursts every 6.000 ms, 1-2 blocks per burst (avg 1.80) |

1. Both streams are driven by a 6 ms hardware period (288 frames), not by the 3.33 ms block. PortAudio splits each period into 160-frame blocks, so the callbacks come in bursts.
2. **The input stream delivers about 1.45x more frames per second than the sample rate.** A real-time stream cannot do that. Cause NOT known: either the driver delivers repeated or stale data, or PortAudio calls back too often. The ring buffer cannot keep up, so SplitStream throws the surplus away by "trimming" (731 trims in file 1, 4162 in file 2 = about 78 per second). Each trim is a jump in the audio = a click. This matches the 447-485 clicks per 20 s capture.
3. The input and output bursts are not in step with each other (two separate clocks). With prefill 1 the second output block of a burst often finds the ring empty: 16-18 % of output blocks are silence (underflow). This matches the 20-22 % zero blocks in the earlier captures.
4. File 1: the input stream stopped delivering at 21.6 s while the output kept running (every block after that was an underflow). Not explained; check whether anything was touched on the sound card at that time.
5. looper.log: RTT 22.99 / 25.99 / 20.32 ms (jitter 13.3 / 4.0 / 12.0 ms). Only the third is near 20 ms. Not at the goal.

## Replay of the ring on the same trace (what a different prefill would have done)
| prefill (blocks) | underflow, file 2 | trims | extra latency |
|---|---|---|---|
| 1 (now) | 16.1 % | 1879 | 0 |
| 2 | 4.5 % | 1542 | +3.3 ms |
| 3 | 1.1 % | 1452 | +6.7 ms |
| 4 | 0.0 % | 1415 | +10 ms |

A bigger prefill removes the underflows but NOT the trims (they come from the 1.45x input surplus), and it costs the latency you want to save. So prefill alone is not the fix, and split mode at 160 cannot be both clean and <= 20 ms on this driver as it behaves now.

## What changed in the code (diagnostic only, behaviour unchanged)
`split_stream.py` now also records, per input block: the driver's ADC time (`adc_ms`), a checksum (`chk`), the total frames delivered, and how many blocks were identical to the one before (repeats). The trace csv has two new columns; the close summary and `stats()` have `in_frames_total` and `in_dup_blocks`.

## What I need from you next (one run, 2 minutes)
Mount Split 48000/160 again, press PLAY for 20 s with the cable and tone as before, unmount, and send the new `logs/split_timing_*.csv` and `looper.log`. The new columns will show whether the input data is real (ADC time advances 3.33 ms per block and no repeats) or stale (repeats, or ADC time moving slower than the block count).
Also useful: the exclusive range matrix, and ASIO4ALL.
