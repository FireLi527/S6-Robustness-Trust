"""Document risk reductions independent of dataset labels and calibration."""
from __future__ import annotations

import numpy as np

ARMS = ("full_mean", "max_window", "top2_mean")


def joint_matrix(task: np.ndarray, content: np.ndarray) -> np.ndarray:
    """Combine paired normalized embeddings without learning extra parameters."""
    if (task.shape != content.shape or task.ndim != 2
            or not np.isfinite(task).all() or not np.isfinite(content).all()):
        raise ValueError("Task/content feature shapes must agree")
    return np.concatenate([task, content, abs(task - content), task * content,
                           np.sum(task * content, axis=1, keepdims=True)], axis=1)


def aggregate_scores(full_score: float, window_scores: np.ndarray) -> dict[str, float]:
    """Return three predeclared reductions, including single-window documents."""
    scores = np.asarray(window_scores)
    if scores.ndim != 1 or not len(scores) or not np.isfinite(scores).all():
        raise ValueError("Window scores must be a nonempty finite vector")
    if not np.isfinite(full_score) or np.any((scores < 0) | (scores > 1)) or not 0 <= full_score <= 1:
        raise ValueError("Expected probability scores")
    top = np.sort(scores)[-min(2, len(scores)):]
    return {"full_mean": float(full_score), "max_window": float(scores.max()),
            "top2_mean": float(top.mean())}
