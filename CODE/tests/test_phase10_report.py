"""Phase 10 / T019: crackle_report + tools/analyze_audio.py turn a capture into an analysis pack.

Every pack here is synthetic (sine + low noise, clicks of known place). Run from CODE/:
    python3 -m unittest tests.test_phase10_report
"""
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
import soundfile as sf

import crackle_report as cr
from tests.test_phase10_crackle_core import sine, inject_clicks, make_blocks

SR = 48000
BLOCK = 64
CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_pack(folder, dur=10.0, n_clicks=14, with_blocks=True, seed=5):
    """A T020-style capture folder: raw.wav, blocks.csv.gz, meta.json. Every click
    sits at offset 1 of a block that was late (a scheduling fault)."""
    os.makedirs(folder, exist_ok=True)
    x = sine(dur, seed=seed)
    rng = np.random.default_rng(9)
    nb = len(x) // BLOCK
    blk = np.sort(rng.choice(np.arange(50, nb - 50), n_clicks, replace=False))
    inject_clicks(x, blk * BLOCK + 1, [3] * n_clicks, [0.3] * n_clicks)
    sf.write(os.path.join(folder, "raw.wav"), x.astype(np.float32), SR, subtype="FLOAT")
    if with_blocks:
        t = make_blocks(len(x), BLOCK, late_idx=blk)
        with gzip.open(os.path.join(folder, "blocks.csv.gz"), "wt") as fh:
            fh.write("index,start,frames,cb_ms,status,adc_time\n")
            for i in range(len(t["start"])):
                fh.write("%d,%d,%d,%.4f,%d,%.6f\n" % (i, t["start"][i], t["frames"][i], t["cb_ms"][i],
                                                       t["status"][i], 100 + i * BLOCK / SR))
    with open(os.path.join(folder, "meta.json"), "w") as fh:
        json.dump({"sample_rate": SR, "block_size": BLOCK}, fh)
    return x


def read_gz_csv(path):
    with gzip.open(path, "rt", newline="") as fh:
        return list(csv.DictReader(fh))


class PackTests(unittest.TestCase):
    """One full run (pictures and excerpts on) shared by the file / format tests."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="t019_")
        cls.pack = os.path.join(cls.tmp, "pack")
        cls.dur = 10.0
        make_pack(cls.pack, cls.dur)
        cls.res = cr.run(cls.pack)
        cls.out = cls.res["out_dir"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_default_output_folder_and_all_files(self):
        self.assertEqual(self.out, os.path.join(self.pack, "analysis"))
        names = set(os.listdir(self.out))
        for n in ["report.json", "report.md", "ms.csv.gz", "events.csv", "report.png",
                  "analysis_pack.zip", "excerpts"] + ["event_%02d.png" % i for i in range(1, 11)]:
            self.assertIn(n, names)
        ex = os.listdir(os.path.join(self.out, "excerpts"))
        self.assertEqual(len(ex), 10)
        self.assertTrue(all(f.endswith(".wav") for f in ex))
        data, sr = sf.read(os.path.join(self.out, "excerpts", "event_01.wav"))
        self.assertEqual(sr, SR)
        self.assertGreater(len(data), SR)            # about +/- 1 s

    def test_ms_csv_one_row_per_millisecond_with_documented_columns(self):
        rows = read_gz_csv(os.path.join(self.out, "ms.csv.gz"))
        self.assertLessEqual(abs(len(rows) - int(self.dur * 1000)), 1)
        self.assertEqual(list(rows[0].keys()), cr.MS_COLUMNS)
        self.assertAlmostEqual(float(rows[5]["t_ms"]), 5.0, places=3)
        self.assertGreater(float(rows[100]["peak"]), 0.25)
        flags = np.array([int(r["flags"]) for r in rows])
        self.assertGreaterEqual(int(np.count_nonzero(flags & cr.FLAG_CLICK)), 10)
        self.assertGreaterEqual(int(np.count_nonzero(flags & cr.FLAG_LATE)), 10)

    def test_events_csv_columns_and_content(self):
        with open(os.path.join(self.out, "events.csv"), newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(list(rows[0].keys()), cr.EVENT_COLUMNS)
        self.assertEqual(len(rows), 14)
        self.assertTrue(all(r["type"] == "click" for r in rows))
        self.assertTrue(all(int(r["offset_in_block"]) == 1 for r in rows))
        self.assertTrue(all(r["block_index"] != "" for r in rows))
        self.assertLess(float(rows[0]["nearest_engine_event_ms"]), 1.0)     # right next to a late block
        self.assertIn(rows[0]["confidence"], ("low", "medium", "high"))

    def test_report_json_keys_and_verdict(self):
        with open(os.path.join(self.out, "report.json"), encoding="utf-8") as fh:
            rj = json.load(fh)
        self.assertEqual(list(rj.keys()), cr.REPORT_KEYS)
        self.assertEqual(rj["verdict"]["top"], "software_scheduling")
        self.assertEqual(rj["verdict"]["confidence"], "high")
        self.assertEqual(rj["counts"]["clicks"], 14)
        self.assertEqual(rj["input"]["block_size"], BLOCK)
        self.assertTrue(rj["input"]["has_blocks"])
        self.assertEqual(rj["pack"]["ms_every"], 1)
        self.assertEqual(len(rj["worst_events"]), 14)
        self.assertNotIn("rank", rj["worst_events"][0])
        self.assertIsNone(rj["band_edges_hz"][-1])                  # inf is stored as null

    def test_report_md_short_and_ordered(self):
        with open(os.path.join(self.out, "report.md"), encoding="utf-8") as fh:
            text = fh.read()
        lines = text.splitlines()
        self.assertLess(len(lines), 150)
        self.assertTrue(lines[0].startswith("# Verdict: software_scheduling"))
        i_ev, i_nt = lines.index("## Evidence"), lines.index("## Next test")
        self.assertGreater(i_ev, 0)
        self.assertGreater(i_nt, i_ev)
        self.assertLess(i_nt, lines.index("## Numbers"))
        self.assertIn("start of the 64-sample block", text)

    def test_zip_contents_and_size(self):
        self.assertLessEqual(self.res["zip_bytes"], 20 * 1024 * 1024)
        with zipfile.ZipFile(self.res["zip"]) as z:
            names = z.namelist()
            self.assertIsNone(z.testzip())
        for n in ("report.md", "report.json", "events.csv", "ms.csv.gz", "report.png",
                  "event_01.png", "excerpts/event_01.wav"):
            self.assertIn(n, names)
        self.assertNotIn("raw.wav", names)


class SizeLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t019_")
        self.pack = os.path.join(self.tmp, "pack")
        make_pack(self.pack, 10.0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ms_table_is_thinned_to_fit_max_mb(self):
        mb = 0.1
        res = cr.run(self.pack, os.path.join(self.tmp, "o1"), max_mb=mb, n_excerpts=0, make_png=False)
        self.assertLessEqual(res["zip_bytes"], mb * 1024 * 1024)
        rj = res["report"]
        self.assertIn(rj["pack"]["ms_every"], (2, 5, 10))
        self.assertLess(rj["pack"]["ms_rows"], 10000)
        self.assertEqual(rj["pack"]["ms_rows"], len(read_gz_csv(os.path.join(res["out_dir"], "ms.csv.gz"))))
        self.assertTrue(any("keeps every" in n for n in rj["notes"]))
        with open(os.path.join(res["out_dir"], "report.md"), encoding="utf-8") as fh:
            self.assertIn("keeps every", fh.read())
        # events must survive the thinning: the click flag is still in the table
        flags = np.array([int(r["flags"]) for r in read_gz_csv(os.path.join(res["out_dir"], "ms.csv.gz"))])
        self.assertGreaterEqual(int(np.count_nonzero(flags & cr.FLAG_CLICK)), 10)

    def test_full_resolution_when_it_fits(self):
        res = cr.run(self.pack, os.path.join(self.tmp, "o2"), max_mb=20, n_excerpts=0, make_png=False)
        self.assertEqual(res["report"]["pack"]["ms_every"], 1)
        self.assertFalse(any("keeps every" in n for n in res["report"]["notes"]))

    def test_excerpts_are_reduced_when_thinning_is_not_enough(self):
        mb = 1.0
        res = cr.run(self.pack, os.path.join(self.tmp, "o3"), max_mb=mb, n_excerpts=10, make_png=False)
        self.assertLessEqual(res["zip_bytes"], mb * 1024 * 1024)
        rj = res["report"]
        self.assertLess(rj["pack"]["excerpts_kept"], 10)
        self.assertEqual(len(os.listdir(os.path.join(res["out_dir"], "excerpts"))), rj["pack"]["excerpts_kept"])
        self.assertTrue(any("audio excerpts kept" in n for n in rj["notes"]))

    def test_impossible_limit_is_reported_not_hidden(self):
        res = cr.run(self.pack, os.path.join(self.tmp, "o4"), max_mb=0.001, n_excerpts=0, make_png=False)
        self.assertTrue(res["report"]["pack"]["over_limit"])
        self.assertTrue(any("above the" in n for n in res["report"]["notes"]))


class OtherInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t019_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_running_twice_gives_identical_report_json(self):
        pack = os.path.join(self.tmp, "pack")
        make_pack(pack, 6.0)
        a = cr.run(pack, os.path.join(self.tmp, "a"), make_png=False)
        b = cr.run(pack, os.path.join(self.tmp, "b"), make_png=False)
        with open(os.path.join(a["out_dir"], "report.json"), "rb") as fa, \
                open(os.path.join(b["out_dir"], "report.json"), "rb") as fb:
            self.assertEqual(fa.read(), fb.read())
        for n in ("report.md", "events.csv", "ms.csv.gz"):
            with open(os.path.join(a["out_dir"], n), "rb") as fa, open(os.path.join(b["out_dir"], n), "rb") as fb:
                self.assertEqual(fa.read(), fb.read(), n)
        # and a rerun into the same folder is also identical
        c = cr.run(pack, a["out_dir"], make_png=False)
        with open(os.path.join(a["out_dir"], "report.json"), "rb") as fa, \
                open(os.path.join(c["out_dir"], "report.json"), "rb") as fc:
            self.assertEqual(fa.read(), fc.read())

    def test_plain_wav_without_blocks_says_correlation_was_not_possible(self):
        x = sine(8.0, seed=2)
        rng = np.random.default_rng(4)
        inject_clicks(x, rng.choice(np.arange(5000, len(x) - 5000, 6000), 8, replace=False), [3] * 8, [0.3] * 8)
        wav = os.path.join(self.tmp, "take.wav")
        sf.write(wav, x.astype(np.float32), SR, subtype="FLOAT")
        res = cr.run(wav, make_png=False, block_size=BLOCK)
        self.assertEqual(res["out_dir"], os.path.join(self.tmp, "take_analysis"))
        rj = res["report"]
        self.assertFalse(rj["input"]["has_blocks"])
        self.assertEqual(rj["input"]["kind"], "file")
        self.assertIsNone(rj["blocks"])
        self.assertTrue(any("not possible" in n and "late blocks" in n for n in rj["notes"]))
        with open(os.path.join(res["out_dir"], "report.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("correlation with late blocks", md)
        self.assertTrue(md.startswith("# Verdict:"))
        with open(os.path.join(res["out_dir"], "events.csv"), newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]["nearest_engine_event_ms"], "")     # no timing table
        self.assertNotEqual(rows[0]["offset_in_block"], "")           # but the block offset is known

    def test_clean_file_gives_clean_verdict(self):
        wav = os.path.join(self.tmp, "clean.wav")
        sf.write(wav, sine(12.0, seed=1).astype(np.float32), SR, subtype="FLOAT")
        res = cr.run(wav, make_png=False, block_size=BLOCK)
        self.assertEqual(res["verdict"]["top"], "clean")
        self.assertEqual(res["report"]["counts"]["events_total"], 0)
        with open(os.path.join(res["out_dir"], "report.md"), encoding="utf-8") as fh:
            self.assertTrue(fh.readline().startswith("# Verdict: clean"))
        self.assertEqual(os.listdir(os.path.join(self.tmp, "clean_analysis")).count("excerpts"), 0)

    def test_compare_mode_blames_the_dsp(self):
        raw = sine(10.0, seed=3)
        proc = raw.copy()
        rng = np.random.default_rng(6)
        pos = rng.choice(np.arange(5000, len(raw) - 5000, 7000), 9, replace=False)
        inject_clicks(proc, pos, [3] * 9, [0.3] * 9)
        pr, pp = os.path.join(self.tmp, "raw.wav"), os.path.join(self.tmp, "processed.wav")
        sf.write(pr, raw.astype(np.float32), SR, subtype="FLOAT")
        sf.write(pp, proc.astype(np.float32), SR, subtype="FLOAT")
        res = cr.run(compare=(pr, pp), make_png=False, block_size=BLOCK)
        self.assertEqual(res["verdict"]["top"], "software_dsp")
        self.assertEqual(res["report"]["input"]["kind"], "compare")
        cm = res["report"]["compare"]
        self.assertEqual(cm["raw"], 0)
        self.assertGreaterEqual(cm["processed_only"], 8)
        self.assertEqual(res["out_dir"], os.path.join(self.tmp, "processed_analysis"))

    def test_compare_mode_blames_the_input_when_raw_has_the_clicks_too(self):
        x = sine(10.0, seed=3)
        rng = np.random.default_rng(6)
        pos = rng.choice(np.arange(5000, len(x) - 5000, 7000), 9, replace=False)
        inject_clicks(x, pos, [3] * 9, [0.3] * 9)
        pr, pp = os.path.join(self.tmp, "raw.wav"), os.path.join(self.tmp, "processed.wav")
        sf.write(pr, x.astype(np.float32), SR, subtype="FLOAT")
        sf.write(pp, x.astype(np.float32), SR, subtype="FLOAT")
        res = cr.run(compare=(pr, pp), make_png=False, block_size=BLOCK)
        self.assertEqual(res["verdict"]["top"], "hardware_or_driver_input")
        self.assertGreaterEqual(res["report"]["compare"]["shared"], 8)

    def test_without_matplotlib_the_pictures_are_skipped_and_the_report_says_so(self):
        pack = os.path.join(self.tmp, "pack")
        make_pack(pack, 6.0)
        real = cr._plt
        cr._plt = lambda: None
        try:
            res = cr.run(pack, os.path.join(self.tmp, "nopng"))
        finally:
            cr._plt = real
        names = os.listdir(res["out_dir"])
        self.assertNotIn("report.png", names)
        self.assertFalse(any(n.endswith(".png") for n in names))
        self.assertIn("analysis_pack.zip", names)
        rj = res["report"]
        self.assertEqual(rj["pack"]["png"], "skipped")
        self.assertTrue(any("matplotlib" in n for n in rj["notes"]))
        with open(os.path.join(res["out_dir"], "report.md"), encoding="utf-8") as fh:
            self.assertIn("matplotlib", fh.read())

    def test_capture_recorder_round_trip(self):
        """A folder written by T020's CaptureRecorder.to_files() is analysed as is."""
        from capture_recorder import CaptureRecorder
        x = sine(5.0, seed=8)
        inject_clicks(x, [40000, 90000, 150000, 200000], [3] * 4, [0.3] * 4)
        rec = CaptureRecorder(SR, BLOCK, 1, 2, max_seconds=6)
        for k in range(len(x) // BLOCK):
            blk = x[k * BLOCK:(k + 1) * BLOCK].astype(np.float32).reshape(-1, 1)
            rec.feed(blk, None, BLOCK, None, None, 0.0, 0.0003)
        folder = os.path.join(self.tmp, "cap")
        rec.to_files(folder)
        res = cr.run(folder, make_png=False)
        rj = res["report"]
        self.assertTrue(rj["input"]["has_blocks"])
        self.assertEqual(rj["input"]["block_size"], BLOCK)
        self.assertEqual(rj["counts"]["clicks"], 4)
        self.assertEqual(rj["blocks"]["n_late"], 0)
        self.assertEqual(rj["blocks"]["n_blocks"], len(x) // BLOCK)

    def test_missing_input_raises(self):
        with self.assertRaises(FileNotFoundError):
            cr.run(os.path.join(self.tmp, "nope"), make_png=False)
        empty = os.path.join(self.tmp, "emptyfolder")
        os.makedirs(empty)
        with self.assertRaises(FileNotFoundError):
            cr.run(empty, make_png=False)


class CommandLineTests(unittest.TestCase):
    def test_tool_runs_on_a_synthetic_pack_folder(self):
        tmp = tempfile.mkdtemp(prefix="t019_")
        try:
            pack = os.path.join(tmp, "pack")
            make_pack(pack, 6.0)
            script = os.path.join(CODE, "tools", "analyze_audio.py")
            cp = subprocess.run([sys.executable, script, pack, "-o", os.path.join(tmp, "out"),
                                 "--max-mb", "5", "--excerpts", "3"],
                                capture_output=True, text=True, cwd=tmp, timeout=300)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertIn("software_scheduling", cp.stdout)
            self.assertIn("analysis_pack.zip", cp.stdout)
            out = os.path.join(tmp, "out")
            for n in ("report.json", "report.md", "ms.csv.gz", "events.csv", "analysis_pack.zip"):
                self.assertTrue(os.path.isfile(os.path.join(out, n)), n)
            self.assertEqual(len(os.listdir(os.path.join(out, "excerpts"))), 3)
            self.assertLessEqual(os.path.getsize(os.path.join(out, "analysis_pack.zip")), 5 * 1024 * 1024)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tool_needs_an_input(self):
        script = os.path.join(CODE, "tools", "analyze_audio.py")
        cp = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("--compare", cp.stderr)


if __name__ == "__main__":
    unittest.main()
