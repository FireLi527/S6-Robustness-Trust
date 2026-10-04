"""Review is not benign; unknown truths and extraction denominators stay explicit."""
import unittest
from s6.prompt_injection.authorization_slots_data import build_rows
from s6.prompt_injection.authorization_slots_evaluation import summarize


class SlotEvaluationTests(unittest.TestCase):
    def test_fixture_counts(self):
        rows = build_rows()
        self.assertEqual(len(rows), 324)
        self.assertEqual(sum(r["label"] is None for r in rows), 18)

    def test_no_human_claim(self):
        self.assertTrue(all("NOT human-reviewed" in r["label_basis"] for r in build_rows()))

    def test_review_not_normal(self):
        rows = [{"id": "risk", "label": 1}]
        p = [{"id": "risk", "decision": "REVIEW", "task_slots": None, "content_slots": None}]
        result = summarize(rows, p)
        self.assertEqual(result["risk_auto_normal"], 0)
        self.assertEqual(result["risk_review"], 1)
        self.assertIsNone(result["selective_accuracy"])

    def test_unknown_truth_excluded(self):
        rows = [{"id": "unknown", "label": None}]
        p = [{"id": "unknown", "decision": "REVIEW", "task_slots": None, "content_slots": None}]
        result = summarize(rows, p)
        self.assertEqual(result["known_labels"], 0)
        self.assertIsNone(result["risk_auto_recall"])

    def test_wrong_id(self):
        with self.assertRaises(ValueError):
            summarize([{"id": "a", "label": 0}], [{"id": "b", "decision": "NORMAL"}])

    def test_unextracted_fields_not_correct(self):
        row = build_rows()[0]
        prediction = {"id": row["id"], "decision": "REVIEW", "task_slots": None, "content_slots": None}
        result = summarize([row], [prediction])
        self.assertEqual(result["extraction"]["both"]["exact_correct"], 0)
        self.assertIsNone(result["extraction"]["task"]["conditional_exact_accuracy"])
