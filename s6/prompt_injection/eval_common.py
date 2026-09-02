"""Shared dataset loading and metric helpers for the prompt-injection evaluate_*.py scripts.

Extracted from evaluate_baseline.py (P1) so evaluate_semantic.py (P2) can
build the same per-split precision/recall/F1/latency/category breakdown for
its rule-only, semantic-only, and hybrid decision frames without duplicating
this logic.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "data" / "bipia" / "generated"
SPLITS_DIR = PROJECT_ROOT / "data" / "bipia" / "splits"
BIPIA_BENCHMARK = PROJECT_ROOT / "external" / "BIPIA" / "benchmark"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {error}") from error
            if not isinstance(record, dict) or not isinstance(record.get("context"), str):
                raise ValueError(f"Record at {path}:{line_number} has no string context")
            records.append(record)
    if not records:
        raise ValueError(f"Dataset is empty: {path}")
    return records


def attack_category(attack_name: str) -> str:
    category, separator, variant = attack_name.rpartition("-")
    if not separator or not variant.isdigit():
        raise ValueError(f"Unexpected BIPIA attack name: {attack_name!r}")
    return category


def load_selected_attacks(dataset_file: Path, manifest_file: Path) -> list[dict]:
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected_names = {attack["attack_name"] for attack in manifest["attacks"]}
    records = load_jsonl(dataset_file)
    selected = [record for record in records if record.get("attack_name") in expected_names]
    observed_names = {record.get("attack_name") for record in selected}
    missing = sorted(expected_names - observed_names)
    if missing:
        raise ValueError(
            f"Generated dataset {dataset_file} is missing manifest attacks: {missing}"
        )
    unexpected_categories = {
        attack_category(str(record["attack_name"])) for record in selected
    } - set(manifest["categories"])
    if unexpected_categories:
        raise ValueError(f"Manifest category mismatch: {sorted(unexpected_categories)}")
    return selected


def _decision_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = frame["decision"].value_counts()
    return {
        decision: int(counts.get(decision, 0))
        for decision in ("ALLOW", "REVIEW", "BLOCK")
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _latency_summary(frame: pd.DataFrame) -> dict[str, float]:
    values = [float(value) for value in frame["latency_ms"]]
    if not values:
        return {"median_ms": 0.0, "p95_ms": 0.0}
    return {
        "median_ms": round(statistics.median(values), 4),
        "p95_ms": round(float(pd.Series(values).quantile(0.95)), 4),
    }


def _attack_groups(frame: pd.DataFrame, column: str) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for name, group in frame.groupby(column, sort=True):
        detected = int(group["decision"].isin(("REVIEW", "BLOCK")).sum())
        groups[str(name)] = {
            "samples": int(len(group)),
            "detection_rate": _rate(detected, len(group)),
            "decisions": _decision_counts(group),
        }
    return groups


def summarize_split(frame: pd.DataFrame) -> dict:
    attacked = frame[frame["ground_truth"] == "ATTACK"]
    clean = frame[frame["ground_truth"] == "CLEAN"]
    true_positive = int(attacked["decision"].isin(("REVIEW", "BLOCK")).sum())
    false_negative = int(len(attacked) - true_positive)
    false_positive = int(clean["decision"].isin(("REVIEW", "BLOCK")).sum())
    true_negative = int(len(clean) - false_positive)
    precision_raw = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall_raw = true_positive / len(attacked) if len(attacked) else 0.0
    precision = round(precision_raw, 4)
    recall = round(recall_raw, 4)
    f1 = (
        round(2 * precision_raw * recall_raw / (precision_raw + recall_raw), 4)
        if precision_raw + recall_raw
        else 0.0
    )
    return {
        "attacked_samples": int(len(attacked)),
        "clean_samples": int(len(clean)),
        "confusion_counts": {
            "true_positive": true_positive,
            "false_negative": false_negative,
            "false_positive": false_positive,
            "true_negative": true_negative,
        },
        "attack_detection_rate": recall,
        "precision": precision,
        "f1": f1,
        "clean_allow_rate": _rate(true_negative, len(clean)),
        "false_positive_rate": _rate(false_positive, len(clean)),
        "human_review_rate": _rate(
            int((frame["decision"] == "REVIEW").sum()), len(frame)
        ),
        "attacked_decisions": _decision_counts(attacked),
        "clean_decisions": _decision_counts(clean),
        "latency": {
            "all": _latency_summary(frame),
            "attacked": _latency_summary(attacked),
            "clean": _latency_summary(clean),
        },
        "by_attack_category": _attack_groups(attacked, "attack_category"),
        "by_position": _attack_groups(attacked, "position"),
    }


def failure_rows(frame: pd.DataFrame) -> pd.DataFrame:
    failures = frame[
        ((frame["ground_truth"] == "ATTACK") & (frame["decision"] == "ALLOW"))
        | ((frame["ground_truth"] == "CLEAN") & (frame["decision"] != "ALLOW"))
    ].copy()
    failures.insert(
        3,
        "failure_type",
        failures.apply(
            lambda row: (
                "MISSED_ATTACK"
                if row["ground_truth"] == "ATTACK"
                else "CLEAN_FALSE_POSITIVE"
            ),
            axis=1,
        ),
    )
    return failures
