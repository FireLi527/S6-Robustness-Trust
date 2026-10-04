"""Target quartets, single-side shortcuts, training boundary and ranking loss."""
import unittest
import numpy as np
import torch
from s6.prompt_injection.authorization_relation_data import build_rows, validate, render
from s6.prompt_injection.authorization_relation_training import pair_indices, paired_penalty, scores
from s6.prompt_injection.verify_authorization_relation_v1 import reconstruct


class RelationTests(unittest.TestCase):
    def test_counts(self):
        result = validate(build_rows())
        self.assertEqual(result["rows"], 540)
        self.assertEqual(result["quartets"], 108)
        self.assertEqual(result["partitions"], {"train": {0: 144, 1: 96}, "calibration": {0: 72, 1: 48}, "test": {0: 108, 1: 72}})

    def test_incomplete_quartet(self):
        with self.assertRaises(ValueError):
            validate(build_rows()[1:])

    def test_label_oracle(self):
        rows = build_rows()
        rows[0]["label"] = 1
        with self.assertRaises(ValueError):
            validate(rows)

    def test_family_leak(self):
        rows = build_rows()
        rows[240]["group_id"] = rows[0]["group_id"]
        with self.assertRaises(ValueError):
            validate(rows)

    def test_template_leak(self):
        rows = build_rows()
        rows[240]["template_id"] = rows[0]["template_id"]
        with self.assertRaises(ValueError):
            validate(rows)

    def test_literal_targets_both_mentioned(self):
        for row in build_rows():
            if row["kind"] == "target":
                self.assertIn(row["audit_only_action_target"], row["task"])
                self.assertIn(row["audit_only_authorized_target"], row["content"])

    def test_human_provenance_not_fabricated(self):
        self.assertTrue(all("NOT human-reviewed" in r["label_basis"] for r in build_rows()))

    def test_pair_train_guard(self):
        with self.assertRaises(ValueError):
            pair_indices([r for r in build_rows() if r["split"] == "test"])

    def test_pair_count(self):
        safe, risk = pair_indices([r for r in build_rows() if r["split"] == "train"])
        self.assertEqual(len(safe), 96)
        self.assertEqual(len(risk), 96)

    def test_pair_loss_direction(self):
        logits = torch.tensor([0., 0.], requires_grad=True)
        paired_penalty(logits, [0], [1]).backward()
        self.assertGreater(logits.grad[0], 0)
        self.assertLess(logits.grad[1], 0)

    def test_mlp_reconstruction(self):
        head = {"kind": "mlp", "feature": "joint", "weights":
                {"0.weight": [[1., 0.]], "0.bias": [0.], "2.weight": [[1.]], "2.bias": [0.]}}
        self.assertEqual(scores(head, {"joint": np.zeros((1, 2))})[0], .5)
        self.assertEqual(reconstruct(head, {"joint": np.zeros((1, 2))})[0], .5)

    def test_same_target_refused(self):
        with self.assertRaises(ValueError):
            render("train", 0, "operation", "same", "same")
