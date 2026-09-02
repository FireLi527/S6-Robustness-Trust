"""Evaluate generated IP102 manifests with the S6 integrity detector."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from integrity_detector import assess_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_ROOT = PROJECT_ROOT / "data" / "ip102_poisoning" / "manifests"
RESULTS_ROOT = PROJECT_ROOT / "results" / "ip102_poisoning"
TRUSTED_MANIFEST = MANIFEST_ROOT / "clean_subset.csv"
CANDIDATES = (
    "clean_subset",
    "label_flip_05",
    "label_flip_10",
    "targeted_0_to_1",
)


def main() -> None:
    assessments: list[dict] = []
    findings: list[dict] = []

    for dataset_name in CANDIDATES:
        candidate_path = MANIFEST_ROOT / f"{dataset_name}.csv"
        assessment = assess_manifest(TRUSTED_MANIFEST, candidate_path)
        assessment_row = asdict(assessment)
        assessment_row.pop("findings")
        assessment_row["dataset"] = dataset_name
        assessment_row["reasons"] = "; ".join(assessment.reasons)
        assessments.append(assessment_row)
        for finding in assessment.findings:
            findings.append({"dataset": dataset_name, **asdict(finding)})

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    assessment_file = RESULTS_ROOT / "manifest_assessments.csv"
    finding_file = RESULTS_ROOT / "flagged_samples.csv"
    summary_file = RESULTS_ROOT / "evaluation_summary.json"

    with assessment_file.open("w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.DictWriter(destination, fieldnames=assessments[0].keys())
        writer.writeheader()
        writer.writerows(assessments)

    with finding_file.open("w", newline="", encoding="utf-8-sig") as destination:
        fields = ("dataset", "sample_id", "finding", "trusted_value", "candidate_value")
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(findings)

    summary = {
        "trusted_manifest": str(TRUSTED_MANIFEST),
        "assessments": assessments,
        "flagged_sample_findings": len(findings),
        "important_limitation": (
            "Exact label-change detection requires an independently trusted baseline. "
            "Distribution checks alone cannot prove that an individual label is correct."
        ),
    }
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("dataset              decision score labels hashes missing unknown drift")
    for row in assessments:
        print(
            f"{row['dataset']:<20} {row['decision']:<8} {row['risk_score']:<5} "
            f"{row['label_changes']:<6} {row['hash_changes']:<6} "
            f"{row['missing_samples']:<7} {row['unknown_samples']:<7} "
            f"{row['distribution_drift']:.3f}"
        )
    print(f"Assessments: {assessment_file}")
    print(f"Flagged samples: {finding_file}")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
