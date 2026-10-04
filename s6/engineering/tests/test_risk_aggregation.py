"""Contracts for the isolated aggregation experiment and reviewed diagnostics."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from s6.engineering.artifacts import read_json
from s6.engineering.text_embeddings import EncodingConfig
from s6.engineering.window_embeddings import WindowTextEncoder, pooled_document
from s6.prompt_injection.aggregation_data import (
    native_development, reviewed_pairs, reviewed_maintenance, maintenance_stress,
)
from s6.prompt_injection.risk_aggregation import aggregate_scores, joint_matrix

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


class AggregationTests(unittest.TestCase):
    def test_top_two_is_not_full_mean(self):
        self.assertEqual(aggregate_scores(.3, np.array([.1, .7, .9])),
                         {"full_mean": .3, "max_window": .9, "top2_mean": .8})

    def test_single_window(self):
        self.assertTrue(all(v == .4 for v in aggregate_scores(.4, np.array([.4])).values()))

    def test_invalid_scores(self):
        for scores in ([], [np.nan], [1.1], [[.2]], [-.1]):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                aggregate_scores(.5, np.array(scores))
        with self.assertRaises(ValueError):
            aggregate_scores(np.nan, np.array([.5]))

    def test_joint_shape_and_values(self):
        task, content = np.array([[1., 0.]]), np.array([[0., 1.]])
        np.testing.assert_array_equal(joint_matrix(task, content), [[1, 0, 0, 1, 1, 1, 0, 0, 0]])
        with self.assertRaises(ValueError):
            joint_matrix(task, content[:, :1])
        with self.assertRaises(ValueError):
            joint_matrix(task, np.array([[np.nan, 0]]))

    def test_pool_checks_and_normalization(self):
        np.testing.assert_allclose(pooled_document(np.eye(2), np.ones(2)), [2**-.5]*2)
        for weights in (np.array([0, 1]), np.ones(3), np.array([np.nan, 1])):
            with self.assertRaises(ValueError):
                pooled_document(np.eye(2), weights)


class ReviewedDataTests(unittest.TestCase):
    def test_native_excludes_test_and_retains_groups(self):
        rows = native_development(ROOT)
        self.assertEqual(len(rows), 118)
        self.assertEqual(sum(r["label"] for r in rows if r["split"] == "validation"), 23)
        tests = [r for r in read_json(ROOT / "data/bipia/native_pairs_v1/samples.json") if r["split"] == "test"]
        self.assertFalse({r["id"] for r in rows} & {r["id"] for r in tests})
        self.assertFalse({r["group_id"] for r in rows} & {r["group_id"] for r in tests})

    def test_reviewed_labels_authoritative(self):
        rows = reviewed_pairs(ROOT)
        self.assertEqual((len(rows), sum(r["label"] for r in rows)), (36, 18))
        source = read_json(ROOT / "data/bipia/repo_file_v2/candidate_batch2.json")["samples"]
        identifier = next(r["sample_id"] for r in source if r["review_number"] == 8)
        self.assertEqual(next(r["label"] for r in rows if r["id"] == identifier), 0)

    def test_maintenance_has_no_fabricated_tasks(self):
        rows = reviewed_maintenance(ROOT)
        self.assertEqual(len(rows), 30)
        self.assertTrue(all(r["task"] is None and r["label"] == 0 for r in rows))

    def test_derived_fixture_provenance(self):
        class Tokenizer:
            def encode(self, text, **kwargs):
                return text.split()
        rows = reviewed_maintenance(ROOT)
        fixtures = maintenance_stress(rows, Tokenizer(), minimum_tokens=768)
        self.assertEqual(len(fixtures), 3)
        for fixture in fixtures:
            self.assertGreaterEqual(len(fixture["content"].split()), 768)
            self.assertIsNone(fixture["task"])
            self.assertEqual(set(fixture["source_ids"]), {r["id"] for r in rows if r["repo"] == fixture["repo"]})
        with self.assertRaises(ValueError):
            maintenance_stress(rows, Tokenizer(), 0)


@unittest.skipUnless((SNAPSHOT / "model.safetensors").exists(), "Optional local MiniLM unavailable")
class WindowEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.encoder = WindowTextEncoder(SNAPSHOT, Path(cls.tmp.name), EncodingConfig())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_matches_frozen_document_pooling(self):
        for text in ("", "Short document.", "The project documentation contains maintenance commands. " * 80):
            vectors, weights, stats = self.encoder.encode_windows(text)
            expected, original = self.encoder.encode_one(text)
            np.testing.assert_allclose(pooled_document(vectors, weights), expected, atol=1e-6)
            self.assertEqual(stats["input_tokens"], original["input_tokens"])
            self.assertEqual(stats["dropped_tokens"], 0)
            self.assertEqual(stats["covered_tokens"], stats["input_tokens"])

    def test_window_cache_round_trip(self):
        first = self.encoder.encode_windows("Window cache round trip")
        again = self.encoder.encode_windows("Window cache round trip")
        np.testing.assert_array_equal(first[0], again[0])
        np.testing.assert_array_equal(first[1], again[1])
        self.assertEqual(first[2]["encoder"], again[2]["encoder"])

    def test_invalid_windows_and_input(self):
        for windows in ([], [(0, 2)], [(-1, 0)]):
            with self.assertRaises(ValueError):
                self.encoder.forward_windows([1], windows)
        with self.assertRaises(TypeError):
            self.encoder.encode_windows(None)
        with self.assertRaises(ValueError):
            self.encoder.encode_windows("a" * (self.encoder.config.max_document_tokens * 16 + 1))
