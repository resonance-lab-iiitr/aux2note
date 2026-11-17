"""Compares current DSP output against tests/golden/baseline_dsp.npz, which
was produced by tools/golden.py on the UNCHANGED v1.1 effects. Phase 3 must
keep these within tolerance (or regenerate on purpose and say why)."""
import os
import unittest
import numpy as np

from tests import _stubs  # noqa: F401
from tools.golden import CASES, render_case

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "baseline_dsp.npz")
# max allowed absolute error, linear. 1e-3 is about -60 dBFS.
TOL = {"delay": 1e-4, "reverb": 1e-3, "compressor": 1e-3, "all_fx": 2e-3}


@unittest.skipUnless(os.path.exists(GOLDEN), "golden file missing: run tools/golden.py")
class GoldenTests(unittest.TestCase):
    def test_cases_match_baseline(self):
        ref = np.load(GOLDEN)
        for name in CASES:
            with self.subTest(case=name):
                got = render_case(name)
                err = float(np.max(np.abs(got - ref[name])))
                self.assertLess(err, TOL.get(name, 1e-3), f"{name}: max error {err:.2e}")


if __name__ == "__main__":
    unittest.main()
