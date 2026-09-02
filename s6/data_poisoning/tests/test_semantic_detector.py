from __future__ import annotations

import unittest
from dataclasses import fields

import numpy as np

from semantic_detector import (
    QUARANTINE_THRESHOLD,
    REVIEW_THRESHOLD,
    SemanticInputRecord,
    assess_semantic,
    detector_metadata,
    fit_trusted_projection,
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


class FitTrustedProjectionTests(unittest.TestCase):
    def test_covers_every_trusted_sample_with_expected_dimensionality(self) -> None:
        rng = np.random.default_rng(4)
        records, embeddings, _ = _clustered_records(rng, ("0", "1", "2"), per_class=20)
        projected = fit_trusted_projection(records, embeddings)
        self.assertEqual(set(projected.keys()), {r.sha256 for r in records})
        for vector in projected.values():
            self.assertEqual(vector.shape, (32,))  # min(PROJECTION_COMPONENTS, embedding_dim)

    def test_deterministic_given_fixed_seed(self) -> None:
        rng = np.random.default_rng(5)
        records, embeddings, _ = _clustered_records(rng, ("0", "1", "2"), per_class=20)
        first = fit_trusted_projection(records, embeddings)
        second = fit_trusted_projection(records, embeddings)
        for sha in first:
            np.testing.assert_array_equal(first[sha], second[sha])

    def test_mislabelled_sample_still_disagrees_with_neighbors_after_projection(self) -> None:
        rng = np.random.default_rng(6)
        records, embeddings, centers = _clustered_records(rng, ("0", "1", "2"), per_class=20)
        poisoned_sample = records[0]
        embeddings[poisoned_sample.sha256] = (
            centers["1"] + rng.normal(size=32) * 0.3
        ).astype("float32")

        projected = fit_trusted_projection(records, embeddings)
        assessment = assess_semantic(records, projected)
        target = next(r for r in assessment.results if r.sample_id == poisoned_sample.sample_id)

        self.assertLess(target.neighbor_label_agreement, 0.5)
        self.assertGreaterEqual(target.risk_score, REVIEW_THRESHOLD)


class DetectorMetadataTests(unittest.TestCase):
    def test_metadata_is_stable_and_complete(self) -> None:
        first = detector_metadata()
        second = detector_metadata()
        self.assertEqual(first, second)
        self.assertEqual(len(first["config_hash"]), 64)
        self.assertIn("version", first)


if __name__ == "__main__":
    unittest.main()
