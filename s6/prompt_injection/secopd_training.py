"""Small public contracts for local SecOPD development experiments."""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from s6.prompt_injection.secopd_data import canonical


def expand_pairs(pairs: list[dict], small_ids: list[str]) -> list[dict]:
    """Validate group isolation and expose only task/body classification inputs."""
    identifiers = [p["id"] for p in pairs]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate pair identifiers")
    groups = {}
    for pair in pairs:
        split = pair["split"]
        if split not in {"train", "validation", "test"}:
            raise ValueError("Unknown split")
        if groups.setdefault(pair["group_id"], split) != split:
            raise ValueError("Group crosses split boundary")
        if any(not isinstance(pair[k], str) or not pair[k].strip()
               for k in ("task", "clean", "attacked")):
            raise ValueError("Missing task or carrier")
    selected = set(small_ids)
    if (not selected or len(selected) != len(small_ids)
            or not selected <= {p["id"] for p in pairs if p["split"] == "train"}):
        raise ValueError("Small subset must contain unique training pair ids")
    selected_groups = {p["group_id"] for p in pairs if p["id"] in selected}
    if any(p["group_id"] in selected_groups and p["id"] not in selected for p in pairs):
        raise ValueError("Small subset must preserve whole groups")
    return [{"id": p["id"] + f"-{label}", "pair_id": p["id"], "task": p["task"],
             "content": p[field], "label": label, "group_id": p["group_id"],
             "split": p["split"], "small": p["id"] in selected}
            for p in pairs for label, field in ((0, "clean"), (1, "attacked"))]


def diagnostic_overlap(rows: list[dict], reference: list[dict]) -> list[str]:
    """Exclude reviewed diagnostics with exact task or >=.88 character similarity."""
    tasks = {canonical(row["task"]) for row in rows}
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), max_features=50000,
                                 dtype=np.float32)
    matrix = vectorizer.fit_transform([r["content"] for r in rows + reference])
    similarities = (matrix[len(rows):] @ matrix[:len(rows)].T).toarray()
    return [r["id"] for i, r in enumerate(reference)
            if canonical(r["task"]) in tasks or similarities[i].max() >= .88]


def paired_correct(predictions: list[dict]) -> dict:
    """Measure success on both members, not just easy clean documents."""
    pairs = {}
    for row in predictions:
        pairs.setdefault(row["pair_id"], []).append(row)
    if any(len(p) != 2 or {r["label"] for r in p} != {0, 1} for p in pairs.values()):
        raise ValueError("Expected one clean and one injected row per pair")
    count = sum(all(r["flag"] == bool(r["label"]) for r in p) for p in pairs.values())
    return {"pairs": len(pairs), "both_correct": count,
            "both_correct_rate": count / len(pairs) if pairs else None}
