"""Contracts for the scale-control experiment."""
import unittest
from s6.prompt_injection.secopd_training import expand_pairs, paired_correct, diagnostic_overlap


def pair(identifier="a", group=0, split="train"):
    return {"id": identifier, "group_id": group, "split": split,
            "task": "Summarize document", "clean": "Original paragraph", "attacked": "Original paragraph + injected instruction",
            "chosen": "Forbidden completion feature"}


class SecopdTrainingTests(unittest.TestCase):
    def test_pair_expansion_excludes_completions(self):
        rows = expand_pairs([pair()], ["a"])
        self.assertEqual([r["label"] for r in rows], [0, 1])
        self.assertTrue(all("chosen" not in r for r in rows))
        self.assertEqual(rows[0]["task"], rows[1]["task"])

    def test_group_leakage_rejected(self):
        with self.assertRaises(ValueError):
            expand_pairs([pair(), pair("b", split="test")], ["a"])

    def test_small_subset_cannot_take_validation(self):
        with self.assertRaises(ValueError):
            expand_pairs([pair(split="validation")], ["a"])

    def test_small_subset_keeps_groups(self):
        with self.assertRaises(ValueError):
            expand_pairs([pair(), pair("b")], ["a"])

    def test_both_members_required(self):
        rows = [{"pair_id": "a", "label": 0, "flag": False}, {"pair_id": "a", "label": 1, "flag": False}]
        self.assertEqual(paired_correct(rows)["both_correct"], 0)
        with self.assertRaises(ValueError):
            paired_correct(rows[:1])

    def test_diagnostic_exact_task_excluded(self):
        rows = [{"id": "a", "task": "Do this", "content": "Example one"}]
        ref = [{"id": "b", "task": " do THIS ", "content": "Completely different"}]
        self.assertEqual(diagnostic_overlap(rows, ref), ["b"])
