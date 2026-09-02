from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from integrity_detector import assess_manifest
from manifest_protocol import CANDIDATE_FIELDS


def _write_manifest(path: Path, labels: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        for index, label in enumerate(labels):
            writer.writerow(
                {
                    "sample_id": f"sample-{index}",
                    "source_relpath": f"{index}.jpg",
                    "sha256": f"hash-{index}",
                    "assigned_label": label,
                }
            )


class CandidateOnlyIntegrityTests(unittest.TestCase):
    def test_detects_label_change_without_original_label_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted = root / "trusted.csv"
            candidate = root / "candidate.csv"
            _write_manifest(trusted, ("0", "0", "1", "1"))
            _write_manifest(candidate, ("0", "1", "1", "1"))
            assessment = assess_manifest(trusted, candidate)
            self.assertEqual(assessment.label_changes, 1)
            self.assertEqual(assessment.decision, "BLOCK")


if __name__ == "__main__":
    unittest.main()
