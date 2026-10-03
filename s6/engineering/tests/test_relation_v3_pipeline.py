"""V3 prompt/records/evaluation helpers without model execution."""
import json
from pathlib import Path
import unittest
from s6.prompt_injection import relation_sft_v3_io as io
from s6.prompt_injection.evaluate_relation_v3 import add_claims_free, summarize, unique_jobs, v1_score

ROOT = Path(__file__).resolve().parents[3]


class FakeTokenizer:
    eos_token_id = 0

    def apply_chat_template(self, messages, **_):
        return [1] * (sum(len(m["content"]) for m in messages) // 4)

    def encode(self, text, add_special_tokens=False):
        return [2] * (len(text) // 4)


class V3PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads((ROOT / "data/bipia/relation_scale_targets_v3/samples.json").read_text(encoding="utf-8"))
        cls.train = [r for r in rows if r["split"] == "train"]
        cls.validation = [r for r in rows if r["split"] == "validation"]

    def gold(self, arm="large_28_v3"):
        return [{"id": r["id"], "side": s, "arm": arm, "text": json.dumps(r["targets"][s], ensure_ascii=False),
                 "finished": True, "inference_id": r["id"],
                 "score": add_claims_free(io.score_text(json.dumps(r["targets"][s]), True, r["inputs"][s], r["targets"][s]),
                                          json.dumps(r["targets"][s]), r["targets"][s])}
                for r in self.validation for s in ("task", "content")]

    def test_prompt_states_v3_norms(self):
        for phrase in ("claims", "simulation", "unmapped", "纯顺序词", "data"):
            self.assertIn(phrase, io.PROMPT)

    def test_demonstration_must_be_training(self):
        with self.assertRaises(ValueError):
            io.messages(self.validation[0], "task", [self.validation[0]])
        request = json.loads(io.messages(self.validation[0], "content")[-1]["content"])
        self.assertEqual(set(request), {"role", "text"})

    def test_records_mask_inputs_and_reject_validation(self):
        records = io.records(FakeTokenizer(), [r for r in self.train if r["variant"] == "core"][:6])
        self.assertTrue(all(any(v != -100 for v in r["labels"]) and r["labels"][0] == -100 for r in records))
        with self.assertRaises(ValueError):
            io.records(FakeTokenizer(), self.validation[:1])

    def test_denominators_and_gold_scores(self):
        self.assertEqual(len(unique_jobs([r for r in self.validation if r["variant"] == "core"])), 24)
        result = summarize(self.gold(), self.validation, ["large_28_v3"])["large_28_v3"]["core"]
        self.assertEqual((result["unique_exact"], result["both_exact"]), (24, 18))
        free = result["claims_excluded_units"]
        self.assertEqual(free["matched"], free["reference"])

    def test_v1_output_cannot_earn_claims(self):
        row = next(r for r in self.validation if r["id"] == "scale-core-003")
        v2_like = {k: v for k, v in row["targets"]["content"].items() if k != "claims"}
        text = json.dumps(v2_like, ensure_ascii=False)
        score = add_claims_free(v1_score(text, True, row, "content"), text, row["targets"]["content"])
        self.assertTrue(score["valid"])
        self.assertFalse(score["exact"])
        self.assertEqual(score["matched_no_claims"], score["reference_no_claims"])

    def test_verifier_rejects_tampered_score(self):
        from s6.prompt_injection.verify_relation_v3 import verify_record

        class Tok(FakeTokenizer):
            def decode(self, ids, skip_special_tokens=True):
                return self.text

        row, tok = self.validation[0], Tok()
        text = json.dumps(row["targets"]["task"], ensure_ascii=False)
        tok.text = text
        score = add_claims_free(io.score_text(text, True, row["inputs"]["task"], row["targets"]["task"]), text, row["targets"]["task"])
        record = {"arm": "large_28_v3", "id": row["id"], "side": "task", "text": text, "finished": True,
                  "input_ids": io.tokens(tok, row, "task"), "generated_token_ids": [5, 0], "score": score}
        verify_record(record, row, [], tok)
        with self.assertRaises(ValueError):
            verify_record({**record, "score": {**score, "exact": not score["exact"]}}, row, [], tok)

    def test_unfinished_output_invalid(self):
        row = self.validation[0]
        self.assertFalse(v1_score("{", False, row, "task")["valid"])
        self.assertFalse(io.score_text("{", False, row["inputs"]["task"], row["targets"]["task"])["valid"])


if __name__ == "__main__":
    unittest.main()
