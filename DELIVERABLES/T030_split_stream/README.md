# T030: Split in/out, trace test (owner steps)

Do one step at a time.
1. Unzip PROJECT_v038.zip, open the CODE folder, run `python main.py` (or run_looper.bat).
2. Audio tab: Driver WASAPI, tick Exclusive and Split in/out, rate 48000, block 160. Input: Line In. Output: Speakers. Green jack to blue jack cable connected.
3. Click MOUNT.
4. Lab tab: type Test tone, 20 s, label trace1. Start. Wait 20 s.
5. Look at Debug > Engine: write down the "split stream" line (underflows).
6. Audio tab: UNMOUNT (the trace is saved now).
7. Send me: every file CODE/logs/split_timing_*.csv, CODE/logs/looper.log and the folder of the Lab capture (meta.json).
