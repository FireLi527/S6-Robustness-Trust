"""Evidence grounding, conservative comparison and malformed-output contracts."""
import json
import unittest
from s6.prompt_injection.instruction_slot_model import grounded_slot, compare, direct_decision, decoded


def response(value, reason="stop"):
    return {"response": {"done": True, "done_reason": reason, "message": {"content": json.dumps(value)}}}


class InstructionSlotTests(unittest.TestCase):
    def test_grounded(self):
        value = {"mode": "execute", "operation": "processing", "target": "A", "evidence": "Do processing on A."}
        self.assertEqual(grounded_slot(response(value), value["evidence"], "task"), value)

    def test_hallucinated_evidence(self):
        value = {"mode": "execute", "operation": "processing", "target": "B", "evidence": "Do processing on B."}
        self.assertIsNone(grounded_slot(response(value), "Do processing on A.", "task"))

    def test_target_not_in_evidence(self):
        value = {"mode": "execute", "operation": "processing", "target": "B", "evidence": "Do processing on A."}
        self.assertIsNone(grounded_slot(response(value), value["evidence"], "task"))

    def test_partial_output(self):
        self.assertIsNone(decoded(response({}, "length")))

    def test_wrong_mode_role(self):
        value = {"mode": "plan_only", "operation": None, "target": None, "evidence": "Make a plan."}
        self.assertIsNone(grounded_slot(response(value), value["evidence"], "content"))

    def test_target_conflict(self):
        a = {"mode": "execute", "operation": "processing", "target": "A"}
        self.assertEqual(compare(a, {**a, "target": "B"})[0], "RISK")

    def test_plan_execution(self):
        self.assertEqual(compare({"mode": "plan_only"}, {"mode": "execute"})[0], "RISK")

    def test_quote(self):
        self.assertEqual(compare({"mode": "quote_only"}, {"mode": "quotation"})[0], "NORMAL")

    def test_unknown_not_normal(self):
        self.assertEqual(compare(None, {"mode": "quotation"})[0], "REVIEW")

    def test_operation_equivalence_review(self):
        a = {"mode": "execute", "operation": "processing", "target": "A"}
        self.assertEqual(compare(a, {**a, "operation": "another name"})[0], "REVIEW")

    def test_direct_evidence(self):
        value = {"decision": "NORMAL", "task_evidence": "abc", "content_evidence": "def"}
        self.assertEqual(direct_decision(response(value), "abc", "def"), "NORMAL")
        self.assertEqual(direct_decision(response(value), "abc", "other"), "REVIEW")
