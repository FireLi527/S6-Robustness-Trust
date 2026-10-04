"""Post-freeze fixture and metric-adapter contracts, no model calls."""
import unittest
from s6.prompt_injection.instruction_slot_data import build_rows
from s6.prompt_injection.instruction_slot_evaluation import summarize_arm


class InstructionDataTests(unittest.TestCase):
    def test_counts(self):
        rows = build_rows()
        self.assertEqual(len(rows), 32)
        self.assertEqual(sum(r["label"] for r in rows), 16)

    def test_provenance(self):
        self.assertTrue(all("NOT human-reviewed" in r["label_basis"] for r in build_rows()))

    def test_direct_metrics_not_slot_scores(self):
        rows = build_rows()[:1]
        p = [{"id": rows[0]["id"], "decision": "NORMAL", "task_slots": None, "content_slots": None}]
        self.assertNotIn("extraction", summarize_arm(rows, p, "direct"))

    def test_adapter_placeholder_not_scored(self):
        rows = build_rows()[:1]
        p = [{"id": rows[0]["id"], "decision": "REVIEW", "task_slots": None, "content_slots": None}]
        self.assertNotIn("excluded", summarize_arm(rows, p, "structured")["extraction"]["task"]["fields"])
