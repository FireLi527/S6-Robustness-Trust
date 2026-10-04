import unittest
from pathlib import Path
from s6.prompt_injection.aggregation_data import native_development, reviewed_pairs
from s6.prompt_injection.prerequisite_protocol import reviewed_candidates, prerequisite_folds, pair_metrics


class PrerequisiteProtocolTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[3]
        self.new = reviewed_candidates(self.root)

    def test_user_labels_not_author_expectations(self):
        self.assertEqual([r["number"] for r in self.new if r["label"] == 0], [1, 4, 5, 9, 12])
        self.assertEqual(sum(r["label"] for r in self.new), 7)
        self.assertTrue(next(r for r in self.new if r["number"] == 8)["conditional"])

    def test_fold_counts_and_no_eval_training(self):
        folds = prerequisite_folds(native_development(self.root), reviewed_pairs(self.root), self.new, [])
        self.assertEqual(len(folds), 6)
        ids = []
        for f in folds:
            self.assertEqual([len(f[k]) for k in ("base_train", "calibration", "extra_train", "evaluation")], [125, 29, 10, 2])
            self.assertFalse(set(f["extra_train"]) & set(f["evaluation"]))
            ids.extend(f["evaluation"])
        self.assertEqual(len(set(ids)), 12)

    def test_cross_family_leakage_rejected(self):
        edge = {"left": self.new[0]["id"], "right": self.new[2]["id"], "reason": "same_task"}
        with self.assertRaises(ValueError):
            prerequisite_folds(native_development(self.root), reviewed_pairs(self.root), self.new, [edge])

    def test_constant_content_cannot_solve_contrasts(self):
        predictions = [{**r, "score": .8, "flag": True} for r in self.new]
        result = pair_metrics(predictions)
        self.assertEqual(result["opposite_label_pairs"], 5)
        self.assertEqual(result["both_correct"], 0)
        self.assertEqual(result["risk_score_higher"], 0)

    def test_perfect_pairs(self):
        predictions = [{**r, "score": .9 if r["label"] else .1, "flag": bool(r["label"])} for r in self.new]
        self.assertEqual(pair_metrics(predictions)["both_correct"], 5)

    def test_incomplete_pairs_rejected(self):
        with self.assertRaises(ValueError):
            pair_metrics([{**r, "score": .5, "flag": True} for r in self.new[:-1]])
