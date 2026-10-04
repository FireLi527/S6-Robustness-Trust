import unittest
from s6.prompt_injection.paired_source_audit import secfid_pairs, aspi_pairs, audit_groups, text_value


class SourceAuditTests(unittest.TestCase):
    def test_no_task_invention(self):
        for value in (None, {}, ""):
            with self.assertRaises(ValueError):
                text_value(value)

    def test_probe_is_not_automatically_attack_label(self):
        row = {"id": "s1", "instruction": "Count names.", "data": {"base": "Amy", "input": "Amy. Who is Bob?"},
               "probe": {"type": "knowledge"}, "metadata": {"task": "counting"}}
        pairs = secfid_pairs([row])
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(r["risk_label"] is None and not r["training_allowed"] for r in pairs))
        self.assertEqual(pairs[0]["task"], row["instruction"])

    def test_aspi_preserves_clarification_not_fake_tool_output(self):
        row = {"suite": "s", "user_task_id": "u", "injection_task_id": "i", "base_prompt": "Read it.",
               "original_prompt": "Read my mail.", "expected_clarification_question": "Read what?",
               "benign_clarification_response": "My mail.",
               "injections": [{"operator": op, "injected_clarification_response": "attack " + op} for op in ("HR", "GS", "CP")]}
        pairs = aspi_pairs([row])
        self.assertEqual(len(pairs), 4)
        self.assertTrue(all(r["clarification_question"] == "Read what?" for r in pairs))
        self.assertTrue(all(not r["training_allowed"] for r in pairs))
        row["injections"] = row["injections"][:2]
        with self.assertRaises(ValueError):
            aspi_pairs([row])

    def test_same_task_or_content_cannot_be_split(self):
        rows = [{"id": "a", "pair_id": "p1", "task": "task one", "content": "first document", "variant": "clean"},
                {"id": "b", "pair_id": "p2", "task": "task one", "content": "second document", "variant": "clean"},
                {"id": "c", "pair_id": "p3", "task": "task two", "content": "second document", "variant": "clean"}]
        stats, groups = audit_groups(rows)
        self.assertEqual(len(set(groups)), 1)
        self.assertEqual(stats["connected_groups"], 1)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            audit_groups([{"id": "a"}, {"id": "a"}])
