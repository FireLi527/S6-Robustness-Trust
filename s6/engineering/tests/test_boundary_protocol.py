"""Fold and threshold contracts; no experiment scripts imported as libraries."""
import unittest
from pathlib import Path
import numpy as np

from s6.prompt_injection.aggregation_data import native_development, reviewed_pairs
from s6.prompt_injection.boundary_protocol import normalized, leakage_edges, ensure_separated, family_folds, source_threshold


class BoundaryProtocolTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalized(" A  Task\n"), "a task")
        with self.assertRaises(ValueError):
            normalized("")

    def test_task_and_near_edges(self):
        rows = [{"id": "a", "group_id": "g1", "task": "Same TASK", "content": "one short note"},
                {"id": "b", "group_id": "g2", "task": "same task", "content": "unrelated text"},
                {"id": "c", "group_id": "g3", "task": "another task", "content": "one short note!"}]
        edges = leakage_edges(rows)
        self.assertIn({"left": "a", "right": "b", "reason": "same_task"}, edges)
        self.assertIn({"left": "a", "right": "c", "reason": "near_content"}, edges)
        with self.assertRaises(ValueError):
            ensure_separated({"train": ["a"], "evaluation": ["c"]}, edges)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            ensure_separated({"train": ["a"], "evaluation": ["a"]}, [])
        with self.assertRaises(ValueError):
            leakage_edges([{"id": "a"}, {"id": "a"}])

    def test_real_family_assignments(self):
        root = Path(__file__).resolve().parents[3]
        reviewed = reviewed_pairs(root)
        folds = family_folds(native_development(root), reviewed, [])
        self.assertEqual(len(folds), 6)
        evaluated = [key for fold in folds for key in fold["evaluation"]]
        self.assertEqual(len(evaluated), len(set(evaluated)))
        self.assertEqual(set(evaluated), {r["id"] for r in reviewed})
        for fold in folds:
            self.assertEqual([len(fold[key]) for key in ("native_train", "native_calibration", "reviewed_train", "reviewed_calibration", "evaluation")], [89, 29, 24, 6, 6])
        with self.assertRaises(ValueError):
            family_folds(native_development(root), reviewed[:-1], [])

    def test_each_source_constrains_threshold(self):
        labels = np.array([0, 1, 0, 1])
        scores = np.array([.2, .7, .8, .9])
        threshold, metrics = source_threshold(labels, scores, np.array(["a", "a", "b", "b"]))
        self.assertEqual(threshold, .9)
        self.assertEqual(metrics["pooled"]["tp"], 1)
        self.assertEqual(metrics["by_source"]["b"]["fp"], 0)

    def test_reject_all_is_available(self):
        threshold, metrics = source_threshold(np.array([0, 1]), np.array([.9, .8]), np.array(["a", "a"]))
        self.assertGreater(threshold, .9)
        self.assertEqual(metrics["pooled"]["tp"], 0)
        self.assertEqual(metrics["pooled"]["fp"], 0)

    def test_bad_calibration_rejected(self):
        for scores in ([.2, np.nan], [.2, 1.1]):
            with self.assertRaises(ValueError):
                source_threshold(np.array([0, 1]), np.array(scores), np.array(["a", "a"]))
        with self.assertRaises(ValueError):
            source_threshold(np.array([0, 1]), np.array([.2, .8]), np.array(["a", "b"]))
