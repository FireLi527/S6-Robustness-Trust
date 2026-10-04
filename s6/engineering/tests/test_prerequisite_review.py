import copy
import unittest
from pathlib import Path
from s6.engineering.artifacts import read_json
from s6.prompt_injection.prerequisite_review import expand_candidates, require_review


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3]
        self.document = read_json(root / "data/bipia/prerequisite_review_v1/candidate_groups.json")
        self.rows = expand_candidates(self.document)

    def test_no_silent_labels_or_splits(self):
        self.assertEqual(len(self.rows), 12)
        self.assertTrue(all(r["label"] is None and r["split"] is None for r in self.rows))

    def test_same_carrier_stays_grouped(self):
        for i in range(0, 12, 2):
            a, b = self.rows[i:i+2]
            self.assertEqual(a["content"], b["content"])
            self.assertEqual(a["group_id"], b["group_id"])
            self.assertNotEqual(a["task"], b["task"])

    def test_missing_review_blocks_training(self):
        with self.assertRaises(ValueError):
            require_review(self.rows, {})

    def test_uncertain_excluded(self):
        decisions = {r["id"]: "normal" for r in self.rows}
        decisions[self.rows[0]["id"]] = "uncertain"
        self.assertEqual(len(require_review(self.rows, decisions)), 11)

    def test_invalid_review_rejected(self):
        with self.assertRaises(ValueError):
            require_review(self.rows, {r["id"]: "model_says_safe" for r in self.rows})

    def test_candidate_prelabel_rejected(self):
        doc = copy.deepcopy(self.document)
        doc["groups"][0]["cases"][0]["label"] = 0
        with self.assertRaises(ValueError):
            expand_candidates(doc)

    def test_missing_translation_rejected(self):
        self.document["groups"][0]["content_zh"] = ""
        with self.assertRaises(ValueError):
            expand_candidates(self.document)
