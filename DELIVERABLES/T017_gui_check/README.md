# T017 GUI check (DONE)

- Full suite under Xvfb: `xvfb-run -a -s "-screen 0 1366x768x24" python3.12 -m unittest discover -s tests -t .` -> 373 tests OK.
- Screenshots (scale 100 percent, 3 tracks with audio): tracks / mixer / audio / debug at 1366x768 and 1920x1080 (`<tab>_<WxH>.png`).
- Observation: at 1366x768 the MASTER FX button text is clipped ("MASTER F") in the top bar; at 1920x1080 it fits.
- Docs (README window tour, CHANGELOG rc11, QA rows M19-M28) were written in the earlier partial sessions.
