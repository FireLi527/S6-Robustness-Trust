import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import intent_comparison as ic
from semantic_detector import text_sha256

class IntentComparisonTests(unittest.TestCase):
    def test_predictor_only_needs_text_and_fixed_prototypes(self):
        names = list(ic.PROTOTYPES)
        embeddings = {text_sha256(ic.PROTOTYPES[name]): np.eye(len(names))[i] for i, name in enumerate(names)}
        text = "Untrusted text; scenario metadata is not an input."
        embeddings[text_sha256(text)] = np.eye(len(names))[3]
        result = ic.predict_intent(text, embeddings)
        self.assertEqual(result["label"], names[3])
        self.assertAlmostEqual(result["similarity"], 1.)
        self.assertEqual(result["question"], ic.PRESETS[names[3]])

    def test_invalid_embeddings_fail_instead_of_fake_prediction(self):
        with self.assertRaises(ValueError):
            ic.unit(np.array([float("nan")]))
        with self.assertRaises(ValueError):
            ic.unit(np.zeros(6))

    def test_metrics_include_review_and_count_false_positives(self):
        m = ic.metrics([True, True, False, False], ["REVIEW", "ALLOW", "BLOCK", "ALLOW"])
        self.assertEqual((m["tp"],m["fn"],m["fp"],m["tn"]), (1,1,1,1))
        self.assertEqual(m["recall"], .5)
        self.assertEqual(m["false_positive_rate"], .5)
        self.assertEqual(m["f1"], .5)

    def test_evaluation_keeps_reference_and_auto_predictions_separate(self):
        def fake_embed(texts, cache):
            return {text_sha256(text): np.ones(6) for text in texts}
        result = ic.evaluate(fake_embed)
        self.assertEqual(result["count"], len(ic.SCENARIOS))
        self.assertEqual(sum(v["count"] for v in result["per_class"].values()), result["count"])
        self.assertEqual(result["correct"], sum(r["reference"] == r["predicted"] for r in result["rows"]))
        self.assertFalse(result["affects_live_policy"])
        self.assertFalse(result["similarity_is_probability"])
        self.assertEqual(set(result["detection"]), {"rule","preset_p2","auto_p2","preset_hybrid","auto_hybrid"})

    def test_stale_report_is_not_displayed_as_current(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.json"
            with patch.object(ic, "OUTPUT", output):
                self.assertEqual(ic.load_report()["status"], "NOT_RUN")
                output.write_text(json.dumps({"signature":"old", "status":"COMPLETE"}))
                self.assertEqual(ic.load_report()["status"], "STALE")
