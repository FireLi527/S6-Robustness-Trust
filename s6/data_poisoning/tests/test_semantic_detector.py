from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from dataclasses import fields

import numpy as np

from semantic_detector import (
    QUARANTINE_THRESHOLD,
    REVIEW_THRESHOLD,
    SemanticInputRecord,
    assess_semantic,
    detector_metadata,
    load_embedding_cache,
    save_embedding_cache,
    extract_embeddings,
)


def _clustered_records(rng: np.random.Generator, classes: tuple[str, ...], per_class: int):
    records: list[SemanticInputRecord] = []
    embeddings: dict[str, np.ndarray] = {}
    centers = {label: rng.normal(size=32) * 5 for label in classes}
    for label in classes:
        for index in range(per_class):
            sha = f"{label}-{index}"
            embeddings[sha] = (centers[label] + rng.normal(size=32) * 0.3).astype("float32")
            records.append(
                SemanticInputRecord(
                    sample_id=f"sample-{label}-{index}",
                    source_relpath=f"{label}/{index}.jpg",
                    sha256=sha,
                    assigned_label=label,
                )
            )
    return records, embeddings, centers


class SemanticInputRecordTests(unittest.TestCase):
    def test_input_record_has_no_hidden_ground_truth_fields(self) -> None:
        field_names = {field.name for field in fields(SemanticInputRecord)}
        self.assertNotIn("original_label", field_names)
        self.assertNotIn("poisoned", field_names)
        self.assertEqual(
            field_names, {"sample_id", "source_relpath", "sha256", "assigned_label"}
        )


class AssessSemanticTests(unittest.TestCase):
    def test_typical_sample_is_allowed(self) -> None:
        rng = np.random.default_rng(1)
        records, embeddings, _ = _clustered_records(rng, ("0", "1", "2"), per_class=20)
        assessment = assess_semantic(records, embeddings)
        target = next(r for r in assessment.results if r.sample_id == "sample-0-5")
        self.assertEqual(target.decision, "ALLOW")
        self.assertLess(target.risk_score, REVIEW_THRESHOLD)

    def test_mislabelled_sample_is_quarantined(self) -> None:
        rng = np.random.default_rng(2)
        records, embeddings, centers = _clustered_records(rng, ("0", "1", "2"), per_class=20)
        # The sample declares label "0" but its image content matches class "1".
        poisoned_sample = records[0]
        embeddings[poisoned_sample.sha256] = (
            centers["1"] + rng.normal(size=32) * 0.3
        ).astype("float32")

        assessment = assess_semantic(records, embeddings)
        target = next(r for r in assessment.results if r.sample_id == poisoned_sample.sample_id)

        self.assertEqual(target.decision, "QUARANTINE")
        self.assertGreaterEqual(target.risk_score, QUARANTINE_THRESHOLD)
        self.assertLess(target.neighbor_label_agreement, 0.5)
        self.assertTrue(target.reasons)

    def test_decision_counts_cover_every_result(self) -> None:
        rng = np.random.default_rng(3)
        records, embeddings, _ = _clustered_records(rng, ("0", "1"), per_class=15)
        assessment = assess_semantic(records, embeddings)
        self.assertEqual(sum(assessment.decision_counts.values()), len(records))


class SemanticRegressionTests(unittest.TestCase):
    def test_rejects_duplicate_images_instead_of_leaking_across_folds(self):
        records, embeddings, _ = _clustered_records(np.random.default_rng(8), ("0", "1"), 10)
        records[1] = replace(records[1], sha256=records[0].sha256)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess_semantic(records, embeddings)

    def test_single_class_and_singleton_do_not_crash_classifier(self):
        records, embeddings, _ = _clustered_records(np.random.default_rng(9), ("0",), 10)
        result = assess_semantic(records, embeddings)
        self.assertTrue(all(r.classifier_confidence is None for r in result.results))
        with self.assertRaisesRegex(ValueError, "at least two"):
            assess_semantic(records[:1], embeddings)

    def test_cache_rejects_changed_embedding_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "embeddings.npz"
            save_embedding_cache(path, {"image": np.ones(512)})
            self.assertIn("image", load_embedding_cache(path))
            with patch("semantic_detector.EMBEDDING_MODEL", "another-model"):
                self.assertEqual(load_embedding_cache(path), {})

    def test_cached_embedding_does_not_hide_changed_image(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sample.png"
            path.write_bytes(b"original")
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            record = SemanticInputRecord("sample", "sample.png", sha, "0")
            cache = root / "cache.npz"
            save_embedding_cache(cache, {sha: np.ones(512)})
            path.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                extract_embeddings([record], root, cache, root)

    def test_nonfinite_embedding_rejected(self):
        records, embeddings, _ = _clustered_records(np.random.default_rng(10), ("0", "1"), 10)
        embeddings[records[0].sha256][0] = np.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            assess_semantic(records, embeddings)


class DetectorMetadataTests(unittest.TestCase):
    def test_metadata_is_stable_and_complete(self) -> None:
        first = detector_metadata()
        second = detector_metadata()
        self.assertEqual(first, second)
        self.assertEqual(len(first["config_hash"]), 64)
        self.assertIn("version", first)


if __name__ == "__main__":
    unittest.main()
