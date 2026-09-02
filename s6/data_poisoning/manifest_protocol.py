"""File-level blind protocol for IP102 candidate data and hidden ground truth."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


CANDIDATE_FIELDS = (
    "sample_id",
    "source_relpath",
    "sha256",
    "assigned_label",
)

HIDDEN_GROUND_TRUTH_FIELDS = (
    "sample_id",
    "original_label",
    "poisoned",
    "poison_type",
)

FORBIDDEN_CANDIDATE_FIELDS = frozenset(HIDDEN_GROUND_TRUTH_FIELDS) - {"sample_id"}


def _read_strict_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        actual_fields = tuple(reader.fieldnames or ())
        if set(actual_fields) != set(expected_fields) or len(actual_fields) != len(expected_fields):
            raise ValueError(
                f"{path} must contain exactly {list(expected_fields)}; found {list(actual_fields)}"
            )
        return list(reader)


def load_candidate_manifest(path: Path) -> list[dict[str, str]]:
    """Load an ingestion manifest that is structurally unable to contain hidden answers."""
    rows = _read_strict_csv(path, CANDIDATE_FIELDS)
    for row_number, row in enumerate(rows, start=2):
        if not all(row[field].strip() for field in CANDIDATE_FIELDS):
            raise ValueError(f"{path}:{row_number} contains an empty candidate field")
    return rows


def load_hidden_ground_truth(path: Path) -> list[dict[str, str]]:
    """Load scoring-only truth. Detectors and training code must never call this function."""
    return _read_strict_csv(path, HIDDEN_GROUND_TRUTH_FIELDS)


def index_unique(rows: Iterable[dict[str, str]], *, source: str) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        sample_id = row["sample_id"]
        if sample_id in indexed:
            raise ValueError(f"{source} contains duplicate sample_id {sample_id!r}")
        indexed[sample_id] = row
    return indexed


def validate_candidate_truth_pair(
    candidate_rows: list[dict[str, str]], truth_rows: list[dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Validate the scoring join after detector predictions have already been frozen."""
    candidate = index_unique(candidate_rows, source="candidate manifest")
    truth = index_unique(truth_rows, source="hidden ground truth")
    if set(candidate) != set(truth):
        missing_truth = sorted(set(candidate) - set(truth))
        unknown_truth = sorted(set(truth) - set(candidate))
        raise ValueError(
            "candidate/ground-truth sample IDs differ: "
            f"{len(missing_truth)} missing truth, {len(unknown_truth)} unknown truth"
        )
    return truth
