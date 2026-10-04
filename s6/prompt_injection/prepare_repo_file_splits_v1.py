"""Freeze near-duplicate-grouped splits for the authorized repository-file data."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sklearn.model_selection import StratifiedGroupKFold

from supervised_data import ROOT


SOURCE = ROOT / "external/prompt-injection-repo-dataset/train.jsonl"
DATA = ROOT / "data/bipia/repo_file_v1"
SEED = 2026
SIMILARITY = 0.88


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def load_source() -> tuple[bytes, list[dict]]:
    raw = SOURCE.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    if len(rows) != 5671 or Counter(r["label"] for r in rows) != {1: 2916, 0: 2755}:
        raise ValueError("Authorized data does not match the audited 5,671-row release")
    if sha(raw) != "7dff37d6aa6812aa1cb8b136da89d651ad78a33a9bd0d06049d51c650f9a8fcc":
        raise ValueError("Authorized source bytes changed since access audit")
    return raw, rows


def grouped_components(texts: list[str]) -> list[int]:
    """Union similar texts; the grouping representation is never trained as a detector."""
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=2,
                                 max_features=150000, dtype=np.float32)
    matrix = vectorizer.fit_transform(texts)
    parent = list(range(len(texts)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        left, right = find(a), find(b)
        if left != right:
            parent[max(left, right)] = min(left, right)

    for start in range(0, len(texts), 128):
        sim = linear_kernel(matrix[start:start + 128], matrix, dense_output=False).tocsr()
        for local in range(sim.shape[0]):
            index = start + local
            begin, end = sim.indptr[local], sim.indptr[local + 1]
            for other, score in zip(sim.indices[begin:end], sim.data[begin:end]):
                if other > index and score >= SIMILARITY:
                    union(index, int(other))
    return [find(i) for i in range(len(texts))]


def prepare() -> None:
    if DATA.exists():
        raise FileExistsError("Repository-file split already frozen")
    raw, rows = load_source()
    texts = [normalized(row["text"]) for row in rows]
    labels = np.asarray([row["label"] for row in rows], dtype=int)
    groups = np.asarray(grouped_components(texts), dtype=int)
    all_indices = np.arange(len(rows))
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    development, test = next(outer.split(all_indices, labels, groups))
    inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=SEED + 1)
    train_local, validation_local = next(inner.split(development, labels[development], groups[development]))
    split_by_index = {int(index): "train" for index in development[train_local]}
    split_by_index.update({int(index): "validation" for index in development[validation_local]})
    split_by_index.update({int(index): "test" for index in test})
    if len(split_by_index) != len(rows):
        raise ValueError("Split assignment incomplete")
    group_sets = {split: {int(groups[index]) for index, assigned in split_by_index.items() if assigned == split}
                  for split in ("train", "validation", "test")}
    if any(group_sets[a] & group_sets[b] for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))):
        raise ValueError("Near-duplicate group leaked across splits")
    assignment_rows = [{"row_index": i, "content_sha256": sha(rows[i]["text"].encode("utf-8")),
                        "group_id": int(groups[i]), "label": int(labels[i]), "split": split_by_index[i]}
                       for i in range(len(rows))]
    DATA.mkdir(parents=True, exist_ok=False)
    assignment_path = DATA / "assignments.csv"
    with assignment_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(assignment_rows[0]))
        writer.writeheader()
        writer.writerows(assignment_rows)
    per_split = {split: {"rows": sum(r["split"] == split for r in assignment_rows),
                         "attacks": sum(r["split"] == split and r["label"] == 1 for r in assignment_rows),
                         "benign": sum(r["split"] == split and r["label"] == 0 for r in assignment_rows),
                         "groups": len(group_sets[split])}
                 for split in ("train", "validation", "test")}
    protocol = {"status": "FROZEN_BEFORE_MODEL_FITTING", "source": "user-provided Hugging Face bucket copy",
                "source_url": "https://huggingface.co/buckets/HXBY527/prompt-injection-repo-dataset-bucket",
                "original_card": "https://huggingface.co/datasets/prodnull/prompt-injection-repo-dataset",
                "source_sha256": sha(raw), "seed": SEED, "grouping": {"kind": "char_tfidf_connected_components",
                "ngram_range": [3, 5], "min_df": 2, "max_features": 150000, "cosine_threshold": SIMILARITY},
                "group_count": len(set(groups)), "largest_group": max(Counter(groups).values()),
                "split_unit": "near-duplicate connected component, not repository or attack family",
                "split_counts": per_split, "assignments_sha256": sha(assignment_path.read_bytes()),
                "preselected_model": {"features": "word TF-IDF (1,2) + char TF-IDF (3,5)",
                                      "classifier": "LogisticRegression(liblinear,class_weight=balanced,C=1,seed=2026)",
                                      "threshold": "choose on validation for max attack recall subject to benign FPR <=5%"},
                "limitations": ["The published JSONL has no repository IDs or attack-family IDs; source/family leakage cannot be ruled out.",
                                "Near-duplicate grouping uses all unlabeled text to define splits, not labels for model fitting.",
                                "Internal test is not an independent-source test; report external stress tests separately."]}
    (DATA / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"groups": protocol["group_count"], "largest_group": protocol["largest_group"],
                      "splits": per_split, "assignments_sha256": protocol["assignments_sha256"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    prepare()
