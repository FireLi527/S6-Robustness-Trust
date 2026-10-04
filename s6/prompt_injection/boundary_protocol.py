"""Group-safe development folds and source-constrained calibration."""
from __future__ import annotations

from difflib import SequenceMatcher
import numpy as np

from s6.engineering.metrics import binary_metrics


def normalized(text: str) -> str:
    """Canonical whitespace/case for task equality and character similarity."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Expected nonempty task/content")
    return " ".join(text.casefold().split())


def leakage_edges(rows: list[dict], threshold: float = .88) -> list[dict]:
    """Connect shared groups/tasks or near text; no model or label inspection."""
    if not 0 < threshold <= 1 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Invalid threshold or duplicate sample identifiers")
    prepared = [(r, normalized(r["task"]), normalized(r["content"])) for r in rows]
    edges = []
    for i, (left, task_a, text_a) in enumerate(prepared):
        for right, task_b, text_b in prepared[i + 1:]:
            reason = None
            if left["group_id"] == right["group_id"]:
                reason = "same_group"
            elif task_a == task_b:
                reason = "same_task"
            elif 2 * min(len(text_a), len(text_b)) / (len(text_a) + len(text_b)) >= threshold:
                ratio = max(SequenceMatcher(None, text_a, text_b, autojunk=False).ratio(),
                            SequenceMatcher(None, text_b, text_a, autojunk=False).ratio())
                if ratio >= threshold:
                    reason = "near_content"
            if reason:
                edges.append({"left": left["id"], "right": right["id"], "reason": reason})
    return edges


def ensure_separated(partitions: dict[str, list[str]], edges: list[dict]) -> None:
    """Reject any duplicated sample or connected pair crossing a fold boundary."""
    owner = {}
    for name, identifiers in partitions.items():
        for identifier in identifiers:
            if identifier in owner:
                raise ValueError(f"Repeated partition identifier: {identifier}")
            owner[identifier] = name
    for edge in edges:
        a, b = edge["left"], edge["right"]
        if a in owner and b in owner and owner[a] != owner[b]:
            raise ValueError(f"Cross-partition leakage: {a}, {b}, {edge['reason']}")


def family_folds(native: list[dict], reviewed: list[dict], edges: list[dict]) -> list[dict]:
    """Six predeclared cyclic folds: held-out family, next calibration, four train."""
    groups = sorted({r["group_id"] for r in reviewed})
    if len(groups) != 6 or len(reviewed) != 36:
        raise ValueError("Expected six reviewed families with 36 examples")
    for group in groups:
        labels = [r["label"] for r in reviewed if r["group_id"] == group]
        if sorted(labels) != [0, 0, 0, 1, 1, 1]:
            raise ValueError("Each family must contain three examples per class")
    if {r["split"] for r in native} != {"train", "validation"}:
        raise ValueError("Native rows must exclude test")
    folds = []
    for index, heldout in enumerate(groups):
        calibration = groups[(index + 1) % len(groups)]
        split = {"native_train": [r["id"] for r in native if r["split"] == "train"],
                 "native_calibration": [r["id"] for r in native if r["split"] == "validation"],
                 "reviewed_train": [r["id"] for r in reviewed if r["group_id"] not in {heldout, calibration}],
                 "reviewed_calibration": [r["id"] for r in reviewed if r["group_id"] == calibration],
                 "evaluation": [r["id"] for r in reviewed if r["group_id"] == heldout]}
        ensure_separated(split, edges)
        folds.append({"fold": index, "heldout_family": heldout, "calibration_family": calibration, **split})
    return folds


def source_threshold(labels: np.ndarray, scores: np.ndarray, sources: np.ndarray,
                     max_fpr: float = .05) -> tuple[float, dict]:
    """Maximize pooled recall under an empirical FPR bound in EACH source."""
    labels, scores, sources = np.asarray(labels), np.asarray(scores), np.asarray(sources)
    if (labels.ndim != 1 or labels.shape != scores.shape or labels.shape != sources.shape
            or not len(labels) or not np.isfinite(scores).all() or not 0 <= max_fpr <= 1
            or np.any((scores < 0) | (scores > 1))):
        raise ValueError("Invalid calibration inputs")
    names = np.unique(sources)
    if any(set(labels[sources == name].tolist()) != {0, 1} for name in names):
        raise ValueError("Each calibration source requires both classes")
    admissible = []
    for threshold in [float(np.nextafter(scores.max(), np.inf)), *map(float, np.unique(scores))]:
        flags = scores >= threshold
        per_source = {str(name): binary_metrics(labels[sources == name], flags[sources == name]) for name in names}
        if all(m["fpr"] <= max_fpr for m in per_source.values()):
            pooled = binary_metrics(labels, flags)
            admissible.append((threshold, {"pooled": pooled, "by_source": per_source}))
    return max(admissible, key=lambda item: (item[1]["pooled"]["recall"], -item[1]["pooled"]["fpr"], item[0]))
