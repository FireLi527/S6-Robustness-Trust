"""Binary detection counts with explicit undefined denominators."""
from __future__ import annotations

import numpy as np


def binary_metrics(labels: np.ndarray, flags: np.ndarray) -> dict:
    labels, flags = np.asarray(labels), np.asarray(flags)
    if labels.ndim != 1 or labels.shape != flags.shape or not len(labels):
        raise ValueError("Expected equal non-empty one-dimensional arrays")
    if not np.isin(labels, [0, 1]).all() or not np.isin(flags, [0, 1]).all():
        raise ValueError("Labels and predictions must be binary")
    tp = int(((labels == 1) & (flags == 1)).sum())
    fp = int(((labels == 0) & (flags == 1)).sum())
    fn = int(((labels == 1) & (flags == 0)).sum())
    tn = int(((labels == 0) & (flags == 0)).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "samples": len(labels),
            "accuracy": (tp + tn) / len(labels), "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None, "fpr": fp / (fp + tn) if fp + tn else None}


def calibrate_threshold(labels: np.ndarray, scores: np.ndarray, max_fpr: float = .05) -> tuple[float, dict]:
    labels, scores = np.asarray(labels), np.asarray(scores)
    if (labels.shape != scores.shape or labels.ndim != 1 or set(labels.tolist()) != {0, 1}
            or not np.isfinite(scores).all() or not 0 <= max_fpr <= 1):
        raise ValueError("Calibration requires both classes, finite scores and a valid FPR bound")
    candidates = [float(np.nextafter(scores.max(), np.inf)), *map(float, np.unique(scores))]
    admissible = []
    for threshold in candidates:
        metrics = binary_metrics(labels, scores >= threshold)
        if metrics["fpr"] <= max_fpr:
            admissible.append((threshold, metrics))
    return max(admissible, key=lambda item: (item[1]["recall"], -item[1]["fpr"], item[0]))
