"""
One command turns a capture into an analysis pack for Claude (Phase 10, T019).

    python3 tools/analyze_audio.py captures/20261111_153000_test
    python3 tools/analyze_audio.py take.wav --block-size 64 --max-mb 10
    python3 tools/analyze_audio.py --compare raw.wav processed.wav

Writes report.md, report.json, ms.csv.gz, events.csv, report.png, event_01..10.png,
excerpts/*.wav and analysis_pack.zip next to the capture (see crackle_report.py).
Attach analysis_pack.zip to a Claude chat.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from crackle_report import main

if __name__ == "__main__":
    sys.exit(main())
