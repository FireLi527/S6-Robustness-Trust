"""Protect directions, negative actions, missing mappings and approval gates."""
import copy
import unittest
from s6.prompt_injection.relation_development_review_v2 import build
from s6.prompt_injection.relation_conversion_v2 import convert
from s6.prompt_injection.relation_contract_v2 import score, validate
from s6.prompt_injection.prepare_relation_sft_v2 import build as build_data
from s6.prompt_injection.relation_sft_v2_io import records, messages, score_text


class RelationV2Tests(unittest.TestCase):
    def setUp(self):
        self.rows = build()[0]

    def test_all_literal_and_exact_self_scores(self):
        for row in self.rows:
            for side, value in convert(row).items():
                validate(value, row[side])
                self.assertTrue(score(value, row[side], value)["exact"])

    def test_no_invented_check_on_24(self):
        value = convert(self.rows[23])["content"]
        self.assertEqual([a["operation"] for a in value["actions"]], ["设为"])
        self.assertEqual(value["actions"][0]["bindings"][0]["status"], "unmapped")

    def test_direction_change_is_wrong(self):
        row = self.rows[17]
        gold = convert(row)["content"]
        value = copy.deepcopy(gold)
        value["actions"][0]["bindings"][0]["role"] = "destination"
        value["actions"][0]["bindings"][1]["role"] = "source"
        self.assertFalse(score(value, row["content"], gold)["exact"])

    def test_negation_change_is_wrong(self):
        row = self.rows[13]
        gold = convert(row)["content"]
        value = copy.deepcopy(gold)
        value["actions"][1]["kind"] = "execute"
        self.assertFalse(score(value, row["content"], gold)["exact"])

    def test_missing_action_reduces_matches(self):
        row = self.rows[11]
        gold = convert(row)["content"]
        value = copy.deepcopy(gold)
        value["actions"].pop()
        result = score(value, row["content"], gold)
        self.assertLess(result["matched"], result["reference"])

    def test_nonliteral_rejected_without_permission(self):
        row = self.rows[0]
        gold = convert(row)["content"]
        value = copy.deepcopy(gold)
        value["actions"][0]["operation"] = "chmod"
        result = score(value, row["content"], gold)
        self.assertFalse(result["valid"])
        self.assertEqual(result["tool_authorization"], "not_granted")

    def test_approved_groups_no_test(self):
        rows, protected = build_data()
        self.assertEqual(sum(r["split"] == "train" for r in rows), 18)
        self.assertEqual(sum(r["split"] == "validation" for r in rows), 6)
        for group in {r["group_id"] for r in rows}:
            self.assertEqual(len({r["split"] for r in rows if r["group_id"] == group}), 1)
        self.assertTrue(any("human_review.json" in p for p in protected))

    def test_no_oracle_current_input(self):
        row = build_data()[0][0]
        current = messages(row, "content")[-1]["content"]
        import json
        self.assertEqual(json.loads(current), {"role": "content", "text": row["inputs"]["content"]})
        reserved = copy.deepcopy(row)
        reserved["split"] = "validation"
        with self.assertRaises(ValueError):
            messages(row, "task", [reserved])

    def test_training_mask_dedup_and_budget(self):
        class Tokenizer:
            eos_token_id = 9
            def apply_chat_template(self, supplied, **kwargs):
                if kwargs.get("return_dict") is not False:
                    raise ValueError("Must request token list")
                return [1, 2, 3]
            def encode(self, text, **kwargs):
                return [4, 5]
        rows = [r for r in build_data()[0] if r["split"] == "train"]
        prepared = records(Tokenizer(), rows)
        self.assertEqual(len(prepared), 24)
        self.assertEqual(prepared[0]["labels"], [-100, -100, -100, 4, 5, 9])
        with self.assertRaises(ValueError):
            records(Tokenizer(), [dict(rows[0], split="validation")])

    def test_incomplete_json_not_valid(self):
        row = self.rows[0]
        expected = convert(row)["content"]
        self.assertFalse(score_text("{}", False, row["content"], expected)["valid"])

    def test_action_order_is_preserved(self):
        row = self.rows[11]
        gold = convert(row)["content"]
        value = copy.deepcopy(gold)
        value["actions"].reverse()
        self.assertFalse(score(value, row["content"], gold)["exact"])


if __name__ == "__main__":
    unittest.main()
