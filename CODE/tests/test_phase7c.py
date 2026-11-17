"""Phase 7c: AUTO default block and the Windows power plan check."""
import unittest

import power_plan as pp
import settings_store as ss


class PowerPlanTests(unittest.TestCase):
    def test_parse_balanced(self):
        t = "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)\r\n"
        self.assertEqual(pp.parse_active_scheme(t), (pp.BALANCED, "Balanced"))

    def test_parse_high_performance_uppercase_guid(self):
        t = "Power Scheme GUID: 8C5E7FDA-E8BF-4A96-9A85-A6E23A8C635C  (High performance)"
        self.assertEqual(pp.parse_active_scheme(t), (pp.HIGH_PERFORMANCE, "High performance"))

    def test_parse_no_name_and_garbage(self):
        self.assertEqual(pp.parse_active_scheme("GUID: " + pp.POWER_SAVER), (pp.POWER_SAVER, ""))
        self.assertIsNone(pp.parse_active_scheme("no guid here"))
        self.assertIsNone(pp.parse_active_scheme(None))

    def test_warning_only_for_slow_plans(self):
        self.assertIn("Balanced", pp.warning_for((pp.BALANCED, "Balanced")))
        self.assertIn("Power saver", pp.warning_for((pp.POWER_SAVER, "Power saver")))
        self.assertIn("High performance", pp.warning_for((pp.BALANCED, "Balanced")))
        self.assertIsNone(pp.warning_for((pp.HIGH_PERFORMANCE, "High performance")))
        self.assertIsNone(pp.warning_for((pp.ULTIMATE, "Ultimate Performance")))
        self.assertIsNone(pp.warning_for(("11111111-2222-3333-4444-555555555555", "My plan")))
        self.assertIsNone(pp.warning_for(None))

    def test_describe(self):
        self.assertIn("n/a", pp.describe(None))
        self.assertIn("Balanced", pp.describe((pp.BALANCED, "Balanced")))

    def test_not_windows_returns_none(self):
        import sys
        if not sys.platform.startswith("win"):
            self.assertIsNone(pp.get_active_scheme())


class AutoDefaultTests(unittest.TestCase):
    def test_auto_is_split_and_not_block_128(self):
        # 128 crackles with split exclusive streams on the test PC (split_test.py)
        a = ss.auto_choice()
        self.assertEqual(a["block_size"], ss.AUTO_BLOCK)
        self.assertEqual(ss.DEFAULT_SETTINGS["block_size"], ss.AUTO_BLOCK)
        self.assertNotEqual(ss.AUTO_BLOCK, 128)
        self.assertIn(ss.AUTO_BLOCK, ss.BLOCK_SIZES)
        self.assertTrue(a["split"])
        self.assertTrue(ss.DEFAULT_SETTINGS["split"])



class DefaultDeviceTests(unittest.TestCase):
    """Regression: a USB webcam microphone (WASAPI, 16000 Hz) became the AUTO input."""

    # Device list as seen on the user's PC after the webcam was plugged in.
    HOSTAPIS = [
        {"name": "MME", "default_input_device": 1, "default_output_device": 4},
        {"name": "Windows DirectSound", "default_input_device": 5, "default_output_device": 8},
        {"name": "ASIO", "default_input_device": 10, "default_output_device": 10},
        {"name": "Windows WASAPI", "default_input_device": 13, "default_output_device": 11},
        {"name": "Windows WDM-KS", "default_input_device": 15, "default_output_device": 14},
    ]
    NAMES = {1: "Line In (Realtek High Definitio", 4: "Speakers (Realtek High Definiti",
             11: "Speakers (Realtek High Definition Audio)",
             12: "Microphone (ZQ-1080RL HD Camera)",
             13: "Line In (Realtek High Definition Audio)"}

    def rows(self, ins, outs):
        return [{"id": i, "name": self.NAMES.get(i, f"dev{i}"),
                 "is_default_in": i in ins, "is_default_out": i in outs}
                for i in range(19)]

    def test_default_ids_cover_every_host_api(self):
        ins, outs = ss.default_device_ids(self.HOSTAPIS, (1, 4))
        self.assertEqual(ins, {1, 5, 10, 13, 15})
        self.assertEqual(outs, {4, 8, 10, 11, 14})

    def test_negative_and_missing_defaults_ignored(self):
        apis = [{"name": "X", "default_input_device": -1, "default_output_device": None}]
        self.assertEqual(ss.default_device_ids(apis, (-1, -1)), (set(), set()))
        self.assertEqual(ss.default_device_ids(None, None), (set(), set()))

    def test_auto_picks_wasapi_line_in_not_the_webcam(self):
        ins, outs = ss.default_device_ids(self.HOSTAPIS, (1, 4))
        rows = self.rows(ins, outs)
        wasapi_in = [(12, "ID 12: Microphone (ZQ-1080RL HD Camera)  [Windows WASAPI]"),
                     (13, "ID 13: Line In (Realtek High Definition Audio)  [Windows WASAPI]")]
        wasapi_out = [(11, "ID 11: Speakers (Realtek High Definition Audio)  [Windows WASAPI]")]
        self.assertEqual(ss.preferred_index(wasapi_in, rows, "is_default_in"), 1)
        self.assertEqual(ss.preferred_index(wasapi_out, rows, "is_default_out"), 0)

    def test_old_behaviour_would_have_failed(self):
        """Only the MME default known (the old rows): the name fallback must still find
        Line In although MME cut its name to 31 characters."""
        rows = self.rows({1}, {4})
        wasapi_in = [(12, "ID 12: Microphone (ZQ-1080RL HD Camera)  [Windows WASAPI]"),
                     (13, "ID 13: Line In (Realtek High Definition Audio)  [Windows WASAPI]")]
        self.assertEqual(ss.preferred_index(wasapi_in, rows, "is_default_in"), 1)

    def test_same_name_helper(self):
        f = ss._same_device_name
        self.assertTrue(f("Line In (Realtek High Definitio", "Line In (Realtek High Definition Audio)"))
        self.assertTrue(f("Speakers (Realtek High Definition Audio)", "Speakers (Realtek High Definition Audio)"))
        self.assertFalse(f("Microphone (ZQ-1080RL HD Camera)", "Line In (Realtek High Definition Audio)"))
        self.assertFalse(f("", "Line In"))
        self.assertFalse(f("Mic", "Microphone (long name here)"))   # too short to trust a prefix


if __name__ == "__main__":
    unittest.main()


class LegacySettingsMigrationTests(unittest.TestCase):
    def test_old_file_gets_split_and_new_block(self):
        got = ss.sanitize({"driver": ss.WASAPI_NAME, "exclusive": True, "split": False,
                           "block_size": 128, "sample_rate": 48000})
        self.assertTrue(got["split"])
        self.assertEqual(got["block_size"], ss.AUTO_BLOCK)

    def test_old_file_other_block_kept(self):
        self.assertEqual(ss.sanitize({"block_size": 256})["block_size"], 256)

    def test_new_file_choice_is_kept(self):
        got = ss.sanitize({"audio_defaults": ss.AUDIO_DEFAULTS_VERSION, "split": False,
                           "block_size": 128})
        self.assertFalse(got["split"])
        self.assertEqual(got["block_size"], 128)
