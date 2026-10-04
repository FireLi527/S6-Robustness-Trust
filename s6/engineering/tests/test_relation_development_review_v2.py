"""Review packaging is not human approval or an independent test set."""
import unittest
from collections import Counter
from s6.prompt_injection.relation_development_review_v2 import build


class DevelopmentReviewTests(unittest.TestCase):
    def test_unique_ids_and_groups(self):
        rows, proposals, _ = build()
        expected = [f"dev2-{i:02d}" for i in range(1, 25)]
        self.assertEqual([r["id"] for r in rows], expected)
        self.assertEqual([p["id"] for p in proposals], expected)
        self.assertEqual(sorted(Counter(r["group_id"] for r in rows).values()), [3] * 8)

    def test_pending_never_ready(self):
        rows, proposals, _ = build()
        self.assertTrue(all(r["split"] == "development_candidate" for r in rows))
        self.assertTrue(all(p["human_status"] == "PENDING" and not p["ready_for_sft"] for p in proposals))
        self.assertTrue(all("proposed_decision" not in r and "human_decision" not in r for r in rows))

    def test_review_contains_inputs_and_fields_without_labels(self):
        rows, proposals, review = build()
        for row, proposal in zip(rows, proposals):
            for value in (row["id"], row["task"], row["content"], proposal["task_scope"], proposal["content_actions"]):
                self.assertIn(value, review)
        for label in ("NORMAL", "RISK", "UNKNOWN"):
            self.assertNotIn(label, review)

    def test_unique_bodies_and_varied_label_order(self):
        rows, proposals, _ = build()
        self.assertEqual(len(set(r["content"] for r in rows)), 24)
        self.assertEqual(Counter(p["proposed_decision"] for p in proposals), {"NORMAL": 8, "RISK": 8, "UNKNOWN": 8})
        orders = {tuple(p["proposed_decision"] for p in proposals[i:i+3]) for i in range(0, 24, 3)}
        self.assertGreater(len(orders), 1)

    def test_deterministic_and_unshared_results(self):
        first = build()
        self.assertEqual(first, build())
        first[0][0]["split"] = "test"
        self.assertEqual(build()[0][0]["split"], "development_candidate")


if __name__ == "__main__":
    unittest.main()
