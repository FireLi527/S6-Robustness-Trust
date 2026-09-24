import unittest
import importlib.util
if importlib.util.find_spec("tensorboard") is None:
    raise unittest.SkipTest("Training-specific tests require the WSL s6-training environment (tensorboard)")
from unittest.mock import patch
from train_stl10_multiseed import expected_protocol, verify
from report_stl10_multiseed import statistics

class MultiseedTests(unittest.TestCase):
    def test_only_seed_changes(self):
        original = {"protocol": {"dataset": "clean_subset", "seed": 2026, "epochs": 20}}
        self.assertEqual(expected_protocol(original, 2027), {"dataset": "clean_subset", "seed": 2027, "epochs": 20})
        self.assertEqual(original["protocol"]["seed"], 2026)

    def test_resume_rejects_wrong_seed_or_settings(self):
        original = {"dataset": "clean_subset", "protocol": {"seed": 2026, "epochs": 20}}
        for protocol in ({"seed": 2026, "epochs": 20}, {"seed": 2027, "epochs": 10}):
            with self.subTest(protocol=protocol), patch("train_stl10_multiseed.validate_run") as validation:
                with self.assertRaisesRegex(ValueError, "Training protocol mismatch"):
                    verify({"dataset": "clean_subset", "protocol": protocol}, original, 2027)
                validation.assert_not_called()

    def test_sample_sd_and_paired_differences(self):
        paired = statistics([a-b for a,b in zip([91,96,101], [90,95,100])])
        self.assertEqual(paired["mean"], 1)
        self.assertEqual(paired["sample_sd"], 0)
        self.assertEqual(paired["values_by_seed"], {2026:1,2027:1,2028:1})
        self.assertEqual(statistics([1,2,3])["sample_sd"], 1)
        with self.assertRaises(ValueError): statistics([1,2])
