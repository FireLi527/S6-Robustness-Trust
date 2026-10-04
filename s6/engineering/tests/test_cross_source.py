"""Cross-source boundaries, weighting and missing-context contracts."""
import unittest
import numpy as np
from s6.prompt_injection.cross_source_data import component_groups, external_overlap, balanced_group_subset
from s6.prompt_injection.cross_source_training import source_class_weights, head_scores, summarize_predictions, training_indices, encode_records
from s6.prompt_injection.verify_cross_source_v1 import validate_partitions


def row(identifier, source="a", label=0, split="train", group="g"):
    return {"id": identifier, "source": source, "label": label, "split": split, "group_id": group,
            "task": "Summarize", "content": "A short paragraph", "flag": False}


class CrossSourceTests(unittest.TestCase):
    def test_verifier_rejects_split_leakage(self):
        with self.assertRaises(ValueError):
            validate_partitions([row("a"), row("b", split="test")], {})

    def test_verifier_rejects_partial_matched_group(self):
        with self.assertRaises(ValueError):
            validate_partitions([row("a"), row("b")], {"a": ["a"]})

    def test_exact_context_group(self):
        rows = [row("a"), {**row("b"), "content": "Different story"}]
        groups, _ = component_groups(rows)
        self.assertEqual(groups[0], groups[1])

    def test_exact_body_group_across_contexts(self):
        rows = [row("a"), {**row("b"), "task": "Translate"}]
        groups, _ = component_groups(rows)
        self.assertEqual(groups[0], groups[1])

    def test_duplicate_identifier_rejected(self):
        with self.assertRaises(ValueError):
            component_groups([row("a"), row("a")])

    def test_overlap_without_context(self):
        self.assertEqual(external_overlap([row("a")], [{**row("b"), "task": None}]), ["b"])

    def test_full_group_subset(self):
        self.assertEqual(set(balanced_group_subset([row("a"), row("b")], 1)), {"a", "b"})

    def test_validation_cannot_enter_subset(self):
        with self.assertRaises(ValueError):
            balanced_group_subset([row("a", split="validation")], 1)

    def test_source_and_class_equal_mass(self):
        rows = [row("a"), row("b", label=1), row("c", source="b"), row("d", source="b"), row("e", source="b", label=1)]
        weights = source_class_weights(rows)
        self.assertAlmostEqual(weights.sum(), 5)
        self.assertAlmostEqual(weights[0], weights[2] + weights[3])

    def test_single_class_training_source_rejected(self):
        with self.assertRaises(ValueError):
            source_class_weights([row("a")])

    def test_binary_head_reconstruction(self):
        head = {"classes": [0, 1], "coef": [[0, 0]], "intercept": [0]}
        np.testing.assert_equal(head_scores(head, np.ones((2, 2))), [.5, .5])
        with self.assertRaises(ValueError):
            head_scores(head, np.ones((2, 3)))

    def test_single_class_metric_interpretation(self):
        result = summarize_predictions([row("a")])
        self.assertIsNone(result["recall"])
        self.assertEqual(result["interpretation"], "FPR-only benign set")

    def test_no_source_pooled_accuracy(self):
        with self.assertRaises(ValueError):
            summarize_predictions([row("a"), row("b", source="b")])

    def test_training_mask_excludes_validation(self):
        rows = [row("a", source="secopd"), row("b", source="spml"), row("c", split="validation")]
        np.testing.assert_equal(training_indices(rows, "mixed_all", {"secopd": ["a"], "spml": ["b"]}), [0, 1])
        with self.assertRaises(ValueError):
            training_indices(rows, "mixed_all", {"secopd": ["c"], "spml": ["b"]})

    def test_taskless_source_has_no_joint_features(self):
        class FakeEncoder:
            def encode_one(self, text):
                if text is None:
                    raise AssertionError("Context must not be invented")
                return np.ones(2), {"dropped_tokens": 0}
        features, stats = encode_records(FakeEncoder(), [{**row("a"), "task": None}], "fixture")
        self.assertEqual(set(features), {"content"})
        self.assertIsNone(stats[0]["task"])
