import unittest
import json
import numpy as np
from experiment_native_pairs_v1 import threshold_for, load, DATA, SOURCE, normalize


class NativePairThresholdTests(unittest.TestCase):
    def test_reject_all_is_available_when_benign_score_is_highest(self):
        threshold, metrics = threshold_for(np.array([0,1]),np.array([.9,.8]))
        self.assertGreater(threshold,.9)
        self.assertEqual(metrics["fp"],0)
        self.assertEqual(metrics["recall"],0)

    def test_selection_maximizes_recall_without_using_test_labels(self):
        threshold, metrics = threshold_for(np.array([0,0,1,1]),np.array([.1,.3,.4,.8]))
        self.assertEqual(threshold,.4)
        self.assertEqual(metrics["recall"],1)
        self.assertEqual(metrics["fpr"],0)


@unittest.skipUnless((DATA / "protocol.json").exists(), "Local optional dataset not prepared")
class NativePairIntegrityTests(unittest.TestCase):
    def test_hashes_and_split_counts_match_frozen_protocol(self):
        protocol, rows = load()
        self.assertEqual(len(rows),147)
        for split in ("train","validation","test"):
            subset = [r for r in rows if r["split"] == split]
            self.assertEqual(sum(r["label"] for r in subset),protocol["counts"][split]["attack"])
            self.assertEqual(sum(1-r["label"] for r in subset),protocol["counts"][split]["benign"])

    def test_groups_and_identical_tasks_cannot_cross_splits(self):
        _, rows = load()
        for field in ("group_id", "task"):
            assignments = {}
            for row in rows:
                key = normalize(row[field])
                assignments.setdefault(key,set()).add(row["split"])
            self.assertTrue(all(len(splits)==1 for splits in assignments.values()))

    def test_pairs_and_labels_are_copied_from_original_fields(self):
        _, rows = load()
        source = {r["id"]:r for r in map(json.loads,SOURCE.read_text(encoding="utf-8").splitlines())}
        for row in rows:
            original = source[row["id"]]
            self.assertEqual(row["task"],original["conversation"][0]["content"])
            self.assertEqual(row["content"],original["conversation"][1]["content"])
            self.assertEqual(row["label"],int(original["ground_truth"] == "unsafe"))
            self.assertNotIn("assistant",row)
            self.assertEqual(original["complexity"],"single_turn")
            self.assertNotEqual(original["injection_surface"],"file_content")

    def test_inspected_example_is_training_only(self):
        _, rows = load()
        row = next(r for r in rows if r["id"] == "AIB-00001")
        self.assertEqual(row["split"],"train")
