"""Evaluate semantic anomaly decisions using physically separate hidden truth."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from manifest_protocol import (
    load_candidate_manifest,
    load_hidden_ground_truth,
    validate_candidate_truth_pair,
)

from semantic_detector import (
    assess_semantic,
    blind_record_from_row,
    detector_metadata,
    extract_embeddings,
    fit_trusted_projection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IP102_ROOT = PROJECT_ROOT / "external" / "IP102"
MANIFEST_ROOT = PROJECT_ROOT / "data" / "ip102_poisoning" / "manifests"
GROUND_TRUTH_ROOT = PROJECT_ROOT / "data" / "ip102_poisoning" / "hidden_ground_truth"
EMBEDDING_CACHE = (
    PROJECT_ROOT / "data" / "ip102_poisoning" / "embeddings" / "clip_vit_b32_embeddings.npz"
)
CLIP_MODEL_CACHE = PROJECT_ROOT / "external" / "clip_cache"
RESULTS_ROOT = PROJECT_ROOT / "results" / "ip102_poisoning"
CANDIDATES = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")


def load_manifest_rows(name: str) -> list[dict[str, str]]:
    return load_candidate_manifest(MANIFEST_ROOT / f"{name}.csv")


def _sample_result_payload(result) -> dict:
    """Serialize detector output without joining hidden evaluation truth."""
    return {
        "decision": result.decision,
        "risk_score": result.risk_score,
        "reasons": list(result.reasons),
        "neighbor_label_agreement": result.neighbor_label_agreement,
        "classifier_confidence": result.classifier_confidence,
        "centroid_distance_z": result.centroid_distance_z,
        "neighbors": [
            {
                "sample_id": neighbor.sample_id,
                "assigned_label": neighbor.assigned_label,
                "distance": round(neighbor.distance, 4),
            }
            for neighbor in result.neighbors
        ],
    }


def evaluate_dataset(
    name: str, rows: list[dict[str, str]], embeddings
) -> tuple[dict, list[dict], dict[str, dict]]:
    records = [blind_record_from_row(row) for row in rows]
    assessment = assess_semantic(records, embeddings)

    # This file is not opened until all detector predictions for the dataset are frozen.
    truth_rows = load_hidden_ground_truth(GROUND_TRUTH_ROOT / f"{name}.csv")
    truth_by_id = validate_candidate_truth_pair(rows, truth_rows)
    poisoned_by_id = {
        sample_id: row["poisoned"].strip().lower() == "true"
        for sample_id, row in truth_by_id.items()
    }

    flagged: list[dict] = []
    sample_results: dict[str, dict] = {}
    y_true: list[bool] = []
    y_score: list[float] = []
    predicted_positive: list[bool] = []
    for result in assessment.results:
        sample_results[result.sample_id] = _sample_result_payload(result)
        truth = poisoned_by_id[result.sample_id]
        y_true.append(truth)
        y_score.append(result.risk_score)
        positive = result.decision != "ALLOW"
        predicted_positive.append(positive)
        if positive:
            flagged.append(
                {
                    "dataset": name,
                    "sample_id": result.sample_id,
                    "decision": result.decision,
                    "risk_score": result.risk_score,
                    "poisoned": truth,
                    "reasons": "; ".join(result.reasons),
                }
            )

    y_true_arr = np.array(y_true)
    predicted_arr = np.array(predicted_positive)
    true_positive = int(np.sum(predicted_arr & y_true_arr))
    false_positive = int(np.sum(predicted_arr & ~y_true_arr))
    false_negative = int(np.sum(~predicted_arr & y_true_arr))
    poisoned_samples = int(y_true_arr.sum())

    if poisoned_samples == 0:
        precision = recall = f1 = None
    else:
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    clean_total = max(int((~y_true_arr).sum()), 1)
    clean_false_positive_rate = false_positive / clean_total

    roc_auc = None
    if len(set(y_true)) > 1:
        roc_auc = float(roc_auc_score(y_true, y_score))

    summary = {
        "dataset": name,
        "samples": len(rows),
        "poisoned_samples": poisoned_samples,
        "decision_counts": assessment.decision_counts,
        "mean_risk_score": round(float(np.mean(y_score)), 4),
        "precision": None if precision is None else round(precision, 4),
        "recall": None if recall is None else round(recall, 4),
        "f1": None if f1 is None else round(f1, 4),
        "clean_false_positive_rate": round(clean_false_positive_rate, 4),
        "roc_auc": None if roc_auc is None else round(roc_auc, 4),
    }
    return summary, flagged, sample_results


def main() -> None:
    all_rows = {name: load_manifest_rows(name) for name in CANDIDATES}
    all_records = [
        blind_record_from_row(row) for rows in all_rows.values() for row in rows
    ]
    embeddings = extract_embeddings(all_records, IP102_ROOT, EMBEDDING_CACHE, CLIP_MODEL_CACHE)

    trusted_records = [blind_record_from_row(row) for row in all_rows["clean_subset"]]
    projected = fit_trusted_projection(trusted_records, embeddings)
    embeddings = {**embeddings, **projected}

    summaries = []
    flagged_all: list[dict] = []
    sample_results_by_dataset: dict[str, dict[str, dict]] = {}
    for name in CANDIDATES:
        summary, flagged, sample_results = evaluate_dataset(name, all_rows[name], embeddings)
        summaries.append(summary)
        flagged_all.extend(flagged)
        sample_results_by_dataset[name] = sample_results

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    assessment_file = RESULTS_ROOT / "semantic_assessments.csv"
    flagged_file = RESULTS_ROOT / "semantic_flagged_samples.csv"
    summary_file = RESULTS_ROOT / "semantic_evaluation_summary.json"
    sample_results_file = RESULTS_ROOT / "semantic_sample_results.json"

    with assessment_file.open("w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.DictWriter(destination, fieldnames=summaries[0].keys())
        writer.writeheader()
        for row in summaries:
            row = dict(row)
            row["decision_counts"] = json.dumps(row["decision_counts"])
            writer.writerow(row)

    with flagged_file.open("w", newline="", encoding="utf-8-sig") as destination:
        fieldnames = ("dataset", "sample_id", "decision", "risk_score", "poisoned", "reasons")
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flagged_all)

    summary_payload = {
        "detector": detector_metadata(),
        "datasets": summaries,
        "flagged_sample_findings": len(flagged_all),
        "important_limitation": (
            "The classifier and centroid signals are fit on each manifest's own "
            "candidate labels, so at very high poison rates the reference statistics "
            "themselves become contaminated. This detector does not require a trusted "
            "baseline manifest for its per-sample decisions, unlike integrity_detector.py, "
            "but its accuracy has only been measured up to a 10% random-flip and a "
            "20%-of-source-class targeted flip rate. Embeddings are now projected with an "
            "NCA (NeighborhoodComponentsAnalysis) fit on clean_subset.csv's trusted labels "
            "(out-of-fold across 5 folds), so the projection itself does rely on that "
            "trusted manifest; it has only "
            "been fit and evaluated on this fixed 1,000-image/5-class benchmark, so its "
            "generalization to genuinely new, unseen images of these classes is untested."
        ),
    }
    summary_file.write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    sample_results_file.write_text(
        json.dumps(
            {
                "detector": detector_metadata(),
                "datasets": sample_results_by_dataset,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("dataset              decisions                               precision recall  f1      clean_fpr auc")
    for row in summaries:
        print(
            f"{row['dataset']:<20} {json.dumps(row['decision_counts']):<38} "
            f"{row['precision']!s:<9} {row['recall']!s:<7} {row['f1']!s:<7} "
            f"{row['clean_false_positive_rate']!s:<9} {row['roc_auc']}"
        )
    print(f"Assessments: {assessment_file}")
    print(f"Flagged samples: {flagged_file}")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
