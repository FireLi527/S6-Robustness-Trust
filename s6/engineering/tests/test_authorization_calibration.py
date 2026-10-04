"""Partition, pairing and fit/calibration boundary contracts."""
import unittest
import numpy as np
from s6.prompt_injection.authorization_calibration_data import build_rows, validate_rows, task_variants, similarity_audit
from s6.prompt_injection.authorization_calibration import fit_head, calibrate, select_head, evaluate
from s6.prompt_injection.verify_authorization_calibration_v1 import recount, choose_threshold, verify_metrics


class AuthorizationCalibrationTests(unittest.TestCase):
    def test_independent_counts(self):
        result = recount([{"label": 1, "flag": True}, {"label": 0, "flag": True}])
        self.assertEqual((result["tp"], result["fp"], result["precision"]), (1, 1, .5))

    def test_independent_threshold(self):
        self.assertEqual(choose_threshold([0, 1, 0, 1], np.array([.1, .8, .2, .9])), .8)

    def test_independent_metric_tampering(self):
        rows = build_rows()[:10]
        result, predictions = evaluate(rows, np.array([r["label"] for r in rows]), .5)
        verify_metrics(predictions, result)
        result["pairs"]["both_correct"] = 0
        with self.assertRaises(ValueError):
            verify_metrics(predictions, result)

    def test_near_duplicate_rejected(self):
        rows = build_rows()
        with self.assertRaises(ValueError):
            similarity_audit(rows, [rows[0]])

    def test_counts_and_family_separation(self):
        rows = build_rows()
        self.assertEqual(len(rows), 240)
        self.assertEqual(validate_rows(rows), {s: {0: 48, 1: 32} for s in ("train", "calibration", "test")})
        self.assertEqual(len({r["group_id"] for r in rows}), 24)

    def test_no_false_human_provenance(self):
        self.assertTrue(all("NOT human-reviewed" in r["label_basis"] for r in build_rows()))

    def test_family_leak_rejected(self):
        rows = build_rows()
        rows[0]["split"] = "test"
        with self.assertRaises(ValueError):
            validate_rows(rows)

    def test_broken_pair_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows(build_rows()[1:])

    def test_body_leak_rejected(self):
        rows = build_rows()
        rows[80]["content"] = rows[0]["content"]
        with self.assertRaises(ValueError):
            validate_rows(rows)

    def test_unknown_template_split(self):
        with self.assertRaises(ValueError):
            task_variants("diagnostic", "action", "other")

    def test_only_train_may_fit(self):
        rows = [r for r in build_rows() if r["split"] == "test"]
        with self.assertRaises(ValueError):
            fit_head(np.zeros((len(rows), 3)), rows, 1.)

    def test_calibration_rejects_seen_rows(self):
        rows = [{"split": "synthetic_diagnostic"}]
        with self.assertRaises(ValueError):
            calibrate({}, np.zeros((1, 3)), rows)

    def test_tie_prefers_stronger_penalty(self):
        heads = {str(c): {"C": c, "calibration_metrics": {"recall": .5, "fpr": 0.}} for c in (1., .1)}
        self.assertEqual(select_head(heads), "0.1")

    def test_eval_pairs_and_quotes(self):
        rows = build_rows()[:10]
        result, _ = evaluate(rows, np.array([r["label"] for r in rows]), .5)
        self.assertEqual(result["pairs"]["both_correct"], 4)
        self.assertEqual(result["by_kind"]["quotation"]["fpr"], 0)

    def test_shape_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(build_rows()[:10], np.zeros(9), .5)

    def test_task_only_target_counterfactual_balance(self):
        rows = build_rows()
        for split in ("train", "calibration", "test"):
            targets = [r for r in rows if r["split"] == split and r["kind"] == "target"]
            for label in (0, 1):
                self.assertEqual(sum("workspace Cedar" in r["task"] for r in targets if r["label"] == label), 4)
