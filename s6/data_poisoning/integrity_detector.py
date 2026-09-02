"""Manifest-based integrity checks for training-data ingestion."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from manifest_protocol import CANDIDATE_FIELDS, load_candidate_manifest


REQUIRED_COLUMNS = set(CANDIDATE_FIELDS)


@dataclass(frozen=True)
class SampleFinding:
    sample_id: str
    finding: str
    trusted_value: str
    candidate_value: str


@dataclass(frozen=True)
class IntegrityAssessment:
    decision: str
    risk_score: int
    reasons: tuple[str, ...]
    trusted_samples: int
    candidate_samples: int
    label_changes: int
    hash_changes: int
    missing_samples: int
    unknown_samples: int
    duplicate_ids: int
    distribution_drift: float
    findings: tuple[SampleFinding, ...]


def load_manifest(path: Path) -> list[dict[str, str]]:
    return load_candidate_manifest(path)


def _distribution(records: list[dict[str, str]]) -> dict[str, float]:
    counts = Counter(record["assigned_label"] for record in records)
    total = max(len(records), 1)
    return {label: count / total for label, count in counts.items()}


def _total_variation(left: dict[str, float], right: dict[str, float]) -> float:
    labels = set(left) | set(right)
    return 0.5 * sum(abs(left.get(label, 0.0) - right.get(label, 0.0)) for label in labels)


def assess_manifest(trusted_path: Path, candidate_path: Path) -> IntegrityAssessment:
    """Compare a candidate manifest with an independently trusted baseline."""
    trusted_rows = load_manifest(trusted_path)
    candidate_rows = load_manifest(candidate_path)

    duplicate_ids = len(candidate_rows) - len({row["sample_id"] for row in candidate_rows})
    trusted = {row["sample_id"]: row for row in trusted_rows}
    candidate = {row["sample_id"]: row for row in candidate_rows}
    findings: list[SampleFinding] = []

    missing_ids = sorted(set(trusted) - set(candidate))
    unknown_ids = sorted(set(candidate) - set(trusted))
    for sample_id in missing_ids:
        findings.append(SampleFinding(sample_id, "missing_sample", "present", "missing"))
    for sample_id in unknown_ids:
        findings.append(SampleFinding(sample_id, "unknown_sample", "absent", "present"))

    label_changes = 0
    hash_changes = 0
    for sample_id in sorted(set(trusted) & set(candidate)):
        trusted_row = trusted[sample_id]
        candidate_row = candidate[sample_id]
        if candidate_row["sha256"] != trusted_row["sha256"]:
            hash_changes += 1
            findings.append(
                SampleFinding(
                    sample_id,
                    "hash_changed",
                    trusted_row["sha256"],
                    candidate_row["sha256"],
                )
            )
        if candidate_row["assigned_label"] != trusted_row["assigned_label"]:
            label_changes += 1
            findings.append(
                SampleFinding(
                    sample_id,
                    "label_changed",
                    trusted_row["assigned_label"],
                    candidate_row["assigned_label"],
                )
            )

    drift = _total_variation(_distribution(trusted_rows), _distribution(candidate_rows))
    comparable_count = max(len(set(trusted) & set(candidate)), 1)
    label_change_rate = label_changes / comparable_count
    score = 0
    reasons: list[str] = []

    if hash_changes:
        score += 6
        reasons.append(f"{hash_changes} file hashes differ from the trusted manifest")
    if missing_ids or unknown_ids:
        score += 6
        reasons.append(
            f"sample membership changed: {len(missing_ids)} missing, {len(unknown_ids)} unknown"
        )
    if duplicate_ids:
        score += 4
        reasons.append(f"{duplicate_ids} duplicate sample identifiers")
    if label_change_rate > 0.02:
        score += 6
        reasons.append(
            f"{label_changes} labels changed ({label_change_rate:.2%}), above the 2% block threshold"
        )
    elif label_changes:
        score += 3
        reasons.append(f"{label_changes} labels changed ({label_change_rate:.2%})")
    if drift > 0.02:
        score += 3
        reasons.append(f"class-distribution drift detected (TV distance {drift:.3f})")

    if score >= 6:
        decision = "BLOCK"
    elif score:
        decision = "REVIEW"
    else:
        decision = "ALLOW"
        reasons.append("candidate matches the trusted manifest")

    return IntegrityAssessment(
        decision=decision,
        risk_score=score,
        reasons=tuple(reasons),
        trusted_samples=len(trusted_rows),
        candidate_samples=len(candidate_rows),
        label_changes=label_changes,
        hash_changes=hash_changes,
        missing_samples=len(missing_ids),
        unknown_samples=len(unknown_ids),
        duplicate_ids=duplicate_ids,
        distribution_drift=drift,
        findings=tuple(findings),
    )
