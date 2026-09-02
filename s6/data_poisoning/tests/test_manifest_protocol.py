from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from manifest_protocol import (
    CANDIDATE_FIELDS,
    HIDDEN_GROUND_TRUTH_FIELDS,
    load_candidate_manifest,
    load_hidden_ground_truth,
    validate_candidate_truth_pair,
)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class CandidateManifestTests(unittest.TestCase):
    def test_candidate_manifest_accepts_only_ingestion_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.csv"
            row = {
                "sample_id": "classification/train/0/a.jpg",
                "source_relpath": "classification/train/0/a.jpg",
                "sha256": "abc",
                "assigned_label": "0",
            }
            _write_csv(path, CANDIDATE_FIELDS, [row])
            self.assertEqual(load_candidate_manifest(path), [row])

    def test_candidate_manifest_rejects_hidden_answer_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leaky.csv"
            fields = CANDIDATE_FIELDS + ("poisoned",)
            row = {
                "sample_id": "a.jpg",
                "source_relpath": "a.jpg",
                "sha256": "abc",
                "assigned_label": "1",
                "poisoned": "True",
            }
            _write_csv(path, fields, [row])
            with self.assertRaisesRegex(ValueError, "must contain exactly"):
                load_candidate_manifest(path)


class HiddenGroundTruthTests(unittest.TestCase):
    def test_truth_can_only_be_joined_by_matching_sample_ids(self) -> None:
        candidates = [
            {
                "sample_id": "a.jpg",
                "source_relpath": "a.jpg",
                "sha256": "abc",
                "assigned_label": "1",
            }
        ]
        truth = [
            {
                "sample_id": "a.jpg",
                "original_label": "0",
                "poisoned": "True",
                "poison_type": "targeted_label_flip",
            }
        ]
        self.assertEqual(validate_candidate_truth_pair(candidates, truth)["a.jpg"], truth[0])
        truth[0]["sample_id"] = "different.jpg"
        with self.assertRaisesRegex(ValueError, "sample IDs differ"):
            validate_candidate_truth_pair(candidates, truth)

    def test_hidden_truth_schema_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truth.csv"
            row = {
                "sample_id": "a.jpg",
                "original_label": "0",
                "poisoned": "False",
                "poison_type": "clean",
            }
            _write_csv(path, HIDDEN_GROUND_TRUTH_FIELDS, [row])
            self.assertEqual(load_hidden_ground_truth(path), [row])


if __name__ == "__main__":
    unittest.main()
