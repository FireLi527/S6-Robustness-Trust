"""Contracts for revised prompts and fresh data, without running a model."""
import json
import unittest
from unittest.mock import patch
from s6.prompt_injection.instruction_slot_fewshot import messages, request, EXAMPLE_INDICES
from s6.prompt_injection.instruction_slot_holdout_v2 import build_rows, OPERATIONS
from s6.prompt_injection.instruction_slot_model import grounded_slot, OPTIONS
from s6.prompt_injection.instruction_slot_trial import run_trial


class FewshotTests(unittest.TestCase):
    def test_role_specific_source_only(self):
        for role in ("task", "content"):
            supplied = messages(role, "CURRENT INPUT")
            self.assertEqual(json.loads(supplied[1]["content"]), {"role": role, "text": "CURRENT INPUT"})
            self.assertIn("Examples:", supplied[0]["content"])
            self.assertNotIn("CURRENT INPUT", supplied[0]["content"])
        self.assertNotEqual(messages("task", "x")[0], messages("content", "x")[0])

    def test_exposed_examples_grounded(self):
        for role in EXAMPLE_INDICES:
            system = messages(role, "x")[0]["content"]
            examples = json.loads(system.split("Examples:\n")[1].split("\nSchema:\n")[0])
            for example in examples:
                record = {"response": {"done": True, "done_reason": "stop", "message": {"content": json.dumps(example["answer"])}}}
                self.assertIsNotNone(grounded_slot(record, example["text"], role))

    def test_invalid_input(self):
        for role, text in (("direct", "x"), ("task", ""), ("content", None)):
            with self.assertRaises(ValueError):
                messages(role, text)

    def test_oversize_rejected_before_network(self):
        with patch("s6.prompt_injection.instruction_slot_fewshot.requests.post") as network:
            with self.assertRaises(ValueError):
                request("task", "x" * 10000)
            network.assert_not_called()

    def test_fresh_rows_fit(self):
        for row in build_rows():
            for role in ("task", "content"):
                size = sum(len(m["content"].encode()) for m in messages(role, row[role])) + 2048 + OPTIONS["num_predict"]
                self.assertLessEqual(size, OPTIONS["num_ctx"])

    def test_fresh_balance_and_quartets(self):
        rows = build_rows()
        self.assertEqual(len(rows), 32)
        self.assertEqual(len({r["id"] for r in rows}), 32)
        self.assertEqual(sum(r["label"] for r in rows), 16)
        self.assertEqual(len(OPERATIONS), 4)
        for family in range(4):
            quartet = [r for r in rows if r["group_id"] == f"fresh-v2-{family}" and r["kind"] == "target"]
            self.assertEqual(len(quartet), 4)
            self.assertEqual(sum(r["label"] for r in quartet), 2)
            for field in ("task", "content"):
                for value in {r[field] for r in quartet}:
                    self.assertEqual({r["label"] for r in quartet if r[field] == value}, {0, 1})

    def test_empty_trial_rejected(self):
        with self.assertRaises(ValueError):
            run_trial(None, None, [], {}, ("direct",))


if __name__ == "__main__":
    unittest.main()
