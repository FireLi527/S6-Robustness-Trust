"""Validated feature, weighting and scoring contracts for cross-source experiments."""
from __future__ import annotations

import numpy as np
from scipy.special import expit
from s6.engineering.metrics import binary_metrics
from s6.engineering.text_embeddings import LocalTextEncoder
from s6.prompt_injection.risk_aggregation import joint_matrix


def source_class_weights(rows: list[dict]) -> np.ndarray:
    """Give each source and each class equal total weight; preserve total sample mass."""
    sources = sorted({r["source"] for r in rows})
    if not rows or any(r["split"] != "train" or r["label"] not in (0, 1) for r in rows):
        raise ValueError("Weights require nonempty binary training rows")
    counts = {(source, label): sum(r["source"] == source and r["label"] == label for r in rows)
              for source in sources for label in (0, 1)}
    if not all(counts.values()):
        raise ValueError("Each training source must have both classes")
    return np.array([len(rows) / (len(sources) * 2 * counts[r["source"], r["label"]]) for r in rows])


def encode_records(encoder: LocalTextEncoder, rows: list[dict], name: str) -> tuple[dict, list[dict]]:
    """Do not invent missing contexts; omit joint features for taskless sources."""
    if not rows or len({r["task"] is None for r in rows}) != 1:
        raise ValueError("Batch must be nonempty and have consistent context availability")
    bodies, tasks, coverage = [], [], []
    for index, row in enumerate(rows):
        body, bs = encoder.encode_one(row["content"])
        ts = None
        bodies.append(body)
        if row["task"] is not None:
            task, ts = encoder.encode_one(row["task"])
            tasks.append(task)
        coverage.append({"id": row["id"], "content": bs, "task": ts})
        if (index + 1) % 200 == 0:
            print(f"{name}: encoded {index + 1}/{len(rows)}", flush=True)
    features = {"content": np.stack(bodies)}
    if tasks:
        features["joint"] = joint_matrix(np.stack(tasks), features["content"])
    return features, coverage


def head_scores(head: dict, features: np.ndarray) -> np.ndarray:
    """Reconstruct binary probability from plain coefficients, without pickle."""
    coef = np.asarray(head["coef"], dtype=np.float64)
    intercept = np.asarray(head["intercept"], dtype=np.float64)
    if (head["classes"] != [0, 1] or features.ndim != 2 or coef.shape != (1, features.shape[1])
            or intercept.shape != (1,) or not np.isfinite(features).all()
            or not np.isfinite(coef).all() or not np.isfinite(intercept).all()):
        raise ValueError("Invalid binary head or feature dimensions")
    return expit(features @ coef[0] + intercept[0])


def predictions(head: dict, features: np.ndarray, rows: list[dict]) -> list[dict]:
    """Store identifiers and scores, never raw prompts or attack objectives."""
    scores = head_scores(head, features)
    if len(scores) != len(rows) or not np.isfinite(head["threshold"]):
        raise ValueError("Invalid prediction rows or threshold")
    return [{**{key: row[key] for key in ("id", "source", "label", "group_id", "split")},
             "score": float(score), "flag": bool(score >= head["threshold"])}
            for row, score in zip(rows, scores, strict=True)]


def summarize_predictions(rows: list[dict]) -> dict:
    """Single-source metrics; single-class sources have explicitly limited meaning."""
    if not rows or len({r["source"] for r in rows}) != 1:
        raise ValueError("Only one nonempty source can be summarized at a time")
    metrics = binary_metrics(np.array([r["label"] for r in rows]), np.array([r["flag"] for r in rows]))
    groups = {}
    for group in sorted({r["group_id"] for r in rows}):
        subset = [r for r in rows if r["group_id"] == group]
        groups[group] = binary_metrics(np.array([r["label"] for r in subset]), np.array([r["flag"] for r in subset]))
    metrics["by_group"] = groups
    labels = {r["label"] for r in rows}
    metrics["interpretation"] = "recall-only attack set" if labels == {1} else "FPR-only benign set" if labels == {0} else "binary classification"
    for key in ("recall", "fpr"):
        defined = [m[key] for m in groups.values() if m[key] is not None]
        metrics[f"macro_group_{key}"] = float(np.mean(defined)) if defined else None
    return metrics


def training_indices(rows: list[dict], scope: str, matched_ids: dict) -> np.ndarray:
    """No held-out/calibration row may enter any model's training mask."""
    if scope not in {"secopd", "spml", "mixed_matched", "mixed_all"}:
        raise ValueError("Unknown training scope")
    matched = set(matched_ids["secopd"] + matched_ids["spml"])
    if not matched <= {r["id"] for r in rows if r["split"] == "train"}:
        raise ValueError("Matched subset contains missing or non-training rows")
    return np.array([i for i, r in enumerate(rows) if r["split"] == "train" and
                     (scope == "mixed_all" or scope == r["source"] or scope == "mixed_matched" and r["id"] in matched)], dtype=int)
