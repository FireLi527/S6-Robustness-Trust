"""Held-out candidate staging: reserved names, balance, no overlap, hidden proposals."""
import unittest
from unittest.mock import patch
from s6.prompt_injection.prepare_relation_holdout_v3 import build, review_text
from s6.prompt_injection.prepare_relation_holdout_v3_targets import approved_labels, build as targets_build


class HoldoutV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.proposals, cls.cores = build()

    def test_counts(self):
        self.assertEqual((len(self.rows), len(self.cores)), (36, 18))
        self.assertEqual(len({c["group_id"] for c in self.cores}), 6)

    def test_nothing_ready(self):
        self.assertTrue(all(not p["ready_for_evaluation"] for p in self.proposals))
        self.assertTrue(all(r["split"] == "sealed_holdout_candidate" for r in self.rows))

    def test_layout_keeps_exact_text(self):
        for core in self.cores:
            layout = next(r for r in self.rows if r["id"] == core["id"] + "-layout")
            self.assertIn(core["content"], layout["content"])
            self.assertEqual(layout["task"], core["task"])

    def test_review_hides_proposed_class(self):
        text = review_text(self.cores)
        for label in ("NORMAL", "RISK", "UNKNOWN"):
            self.assertNotIn(label, text)

    def test_inputs_carry_no_labels(self):
        self.assertTrue(all("label" not in r and "proposed_decision" not in r for r in self.rows))

    def test_draft_references_validate(self):
        labels = {c["id"]: c["label"] for c in self.cores}
        samples = targets_build(self.rows, labels)
        self.assertEqual(len(samples), 36)
        self.assertTrue(all(s["targets"]["content"]["actions"] for s in samples))

    def test_gate_requires_scope_and_action_approval(self):
        review = {"human_decisions": {"NORMAL": [c["id"] for c in self.cores]}, "batch_review_complete": True,
                  "scope_approved_ids": [], "actions_approved_ids": [],
                  "inputs_sha256": "x", "proposals_sha256": "x", "review_sha256": "x"}
        cores = {c["id"] for c in self.cores}
        with patch("s6.prompt_injection.prepare_relation_holdout_v3_targets.require_hash"):
            with self.assertRaises(ValueError):
                approved_labels(review, cores)
            review.update(scope_approved_ids=sorted(cores), actions_approved_ids=sorted(cores))
            self.assertEqual(len(approved_labels(review, cores)), 18)


if __name__ == "__main__":
    unittest.main()
