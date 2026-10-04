"""Small supervised heads and validation-only selection; frozen encoders."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from s6.engineering.metrics import binary_metrics, calibrate_threshold
from s6.prompt_injection.authorization_probe import pair_summary
from s6.prompt_injection.cross_source_training import head_scores

CS = (.01, .1, 1., 10.)
FEATURES = ("content", "task_only", "joint", "nli")


def fit_head(features: np.ndarray, rows: list[dict], c: float) -> dict:
    """L2-regularized LR; train rows only, with deterministic balanced classes."""
    if (not rows or any(r["split"] != "train" for r in rows) or len(features) != len(rows)
            or set(r["label"] for r in rows) != {0, 1} or c not in CS or not np.isfinite(features).all()):
        raise ValueError("Invalid training inputs")
    model = LogisticRegression(C=c, penalty="l2", class_weight="balanced", solver="liblinear",
                               random_state=2026, max_iter=2000).fit(features, [r["label"] for r in rows])
    if int(model.n_iter_.max()) >= 2000:
        raise RuntimeError("Head did not converge")
    return {"classes": model.classes_.tolist(), "coef": model.coef_.tolist(),
            "intercept": model.intercept_.tolist(), "C": c, "iterations": int(model.n_iter_.max())}


def calibrate(head: dict, features: np.ndarray, rows: list[dict]) -> dict:
    """No diagnostics or test labels accepted by the calibration entry point."""
    if not rows or any(r["split"] != "calibration" for r in rows) or len(features) != len(rows):
        raise ValueError("Calibration partition required")
    threshold, metrics = calibrate_threshold(np.array([r["label"] for r in rows]), head_scores(head, features), .05)
    return {**head, "threshold": threshold, "calibration_metrics": metrics}


def select_head(heads: dict[str, dict]) -> str:
    """Predeclared tie break: recall, fewer FPs, then stronger regularization."""
    if not heads:
        raise ValueError("No candidate heads")
    return max(heads, key=lambda name: (heads[name]["calibration_metrics"]["recall"],
                                       -heads[name]["calibration_metrics"]["fpr"], -heads[name]["C"]))


def evaluate(rows: list[dict], scores: np.ndarray, threshold: float) -> tuple[dict, list[dict]]:
    """Keep all counts, paired outcomes, and quoted-control FPR visible."""
    scores = np.asarray(scores)
    if scores.shape != (len(rows),) or not len(rows) or not np.isfinite(scores).all() or not np.isfinite(threshold):
        raise ValueError("Invalid evaluation inputs")
    predictions = [{"id": r["id"], "group_id": r["group_id"], "split": r["split"], "label": r["label"],
                    "pair_id": r.get("pair_id"), "kind": r.get("kind", r.get("wording", "old")),
                    "score": float(s), "flag": bool(s >= threshold)} for r, s in zip(rows, scores, strict=True)]
    def metrics(subset: list[dict]) -> dict:
        return binary_metrics(np.array([r["label"] for r in subset]), np.array([r["flag"] for r in subset]))
    result = {**metrics(predictions), "pairs": pair_summary(predictions)}
    result["by_kind"] = {kind: metrics([r for r in predictions if r["kind"] == kind])
                         for kind in sorted({r["kind"] for r in predictions})}
    result["by_group"] = {group: metrics([r for r in predictions if r["group_id"] == group])
                          for group in sorted({r["group_id"] for r in predictions})}
    return result, predictions
