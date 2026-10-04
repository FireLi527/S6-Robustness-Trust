"""Explicit role mappings and metadata-only leakage checks for cross-source study."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupShuffleSplit
from s6.engineering.artifacts import read_json
from s6.prompt_injection.secopd_data import canonical


def order_key(value: str) -> str:
    """Stable, score-independent ordering for this version."""
    return hashlib.sha256(f"cross-v1-2026:{value}".encode()).hexdigest()


def spml_rows(path: Path, per_class: int = 1600) -> tuple[list[dict], dict]:
    """Keep explicit system context; never treat SPML labels as unconditional malice."""
    if per_class < 1:
        raise ValueError("Positive sample count required")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        raw = list(csv.DictReader(stream))
    valid, excluded, duplicates = [], [], []
    seen = {}
    for index, row in enumerate(raw):
        if row["Prompt injection"] not in {"0", "1"}:
            raise ValueError("Unknown upstream SPML label")
        task, content = row["System Prompt"], row["User Prompt"]
        if not task.strip() or not content.strip():
            excluded.append(index)
            continue
        key = canonical(task), canonical(content)
        label = int(row["Prompt injection"])
        if key in seen:
            if seen[key] != label:
                raise ValueError("Conflicting SPML labels for identical context/body")
            duplicates.append(index)
            continue
        seen[key] = label
        valid.append({"id": f"spml-{index:05}", "source": "spml", "task": task, "content": content,
                      "label": label, "role": "system_context/user_input", "original_index": index})
    selected = []
    for label in (0, 1):
        candidates = sorted([r for r in valid if r["label"] == label], key=lambda r: order_key(r["id"]))
        if len(candidates) < per_class:
            raise ValueError("Insufficient SPML rows for fixed class-balanced sample")
        selected.extend(candidates[:per_class])
    return selected, {"raw": len(raw), "valid_unique": len(valid), "missing_excluded": excluded,
                      "exact_duplicates_removed": duplicates, "sampled_per_class": per_class,
                      "definition": "label is conflict with upstream system prompt; synthetic English, not independent human review"}


def component_groups(rows: list[dict], threshold: float = .88) -> tuple[list[int], dict]:
    """Join exact contexts/bodies and character near-duplicates in either field."""
    if not rows or not 0 < threshold <= 1 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Nonempty unique identifiers and valid threshold required")
    parent = list(range(len(rows)))
    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)
    edges = {}
    for field in ("task", "content"):
        texts, indices, seen = [], [], {}
        for i, row in enumerate(rows):
            text = canonical(row[field])
            if text in seen:
                union(i, seen[text])
            else:
                seen[text] = i
                texts.append(text)
                indices.append(i)
        matrix = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), max_features=50000,
                                 dtype=np.float32).fit_transform(texts)
        count = 0
        for start in range(0, len(texts), 64):
            similarity = (matrix[start:start + 64] @ matrix.T).tocoo()
            for a, b, score in zip(similarity.row, similarity.col, similarity.data, strict=True):
                if start + a < b and score >= threshold:
                    union(indices[start + a], indices[b])
                    count += 1
        edges[field] = count
    groups = [find(i) for i in range(len(rows))]
    sizes = np.unique(groups, return_counts=True)[1]
    return groups, {"groups": len(sizes), "largest_rows": int(sizes.max()), "near_edge_counts": edges,
                    "rule": "exact context/body OR char3-5 TFIDF50k cosine>=.88 within either field; connected components"}


def split_spml(rows: list[dict], old_rows: list[dict]) -> tuple[list[dict], dict]:
    """Remove components touching old data; split remaining components only once."""
    groups, audit = component_groups(rows + old_rows)
    old_groups = set(groups[len(rows):])
    excluded = [r["id"] for r, g in zip(rows, groups[:len(rows)], strict=True) if g in old_groups]
    clean = [{**r, "group_id": f"spml-group-{g}"} for r, g in zip(rows, groups[:len(rows)], strict=True) if g not in old_groups]
    preview_contexts = {r["task"] for r in rows if r["original_index"] < 20}
    forced = {r["group_id"] for r in clean if r["task"] in preview_contexts}
    eligible = np.array([i for i, r in enumerate(clean) if r["group_id"] not in forced])
    group_ids = np.array([r["group_id"] for r in clean])
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=2026).split(eligible, groups=group_ids[eligible]))
    rest = eligible[trainval]
    train, validation = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=2026).split(rest, groups=group_ids[rest]))
    owners = {int(i): name for name, indices in (("train", rest[train]), ("validation", rest[validation]), ("test", eligible[test])) for i in indices}
    result = [{**r, "split": owners.get(i, "train")} for i, r in enumerate(clean)]
    counts = {}
    for split in ("train", "validation", "test"):
        labels = [r["label"] for r in result if r["split"] == split]
        counts[split] = {str(label): labels.count(label) for label in (0, 1)}
        if min(counts[split].values()) < 50:
            raise ValueError("Fixed split has fewer than 50 examples of a class; requires protocol review")
    return result, {**audit, "old_overlap_excluded": excluded, "forced_train_groups": sorted(forced), "counts": counts}


def external_rows(folder: Path) -> tuple[list[dict], dict]:
    """InjecAgent supplies attacks only; NotInject supplies benign text without tasks."""
    rows, seen, duplicates = [], set(), []
    for kind in ("dh", "ds"):
        raw = read_json(folder / f"injecagent/data/test_cases_{kind}_base.json")
        for index, row in enumerate(raw):
            task, content = row["User Instruction"], row["Tool Response"]
            if not task.strip() or not content.strip() or row["Attacker Instruction"] not in content:
                raise ValueError("Invalid InjecAgent field mapping")
            key = canonical(task), canonical(content)
            identifier = f"injecagent-{kind}-{index:04}"
            if key in seen:
                duplicates.append(identifier)
                continue
            seen.add(key)
            rows.append({"id": identifier, "source": "injecagent", "task": task, "content": content,
                         "label": 1, "group_id": row["User Tool"], "split": "external", "role": "user_task/tool_response"})
    for tier in ("one", "two", "three"):
        raw = pq.read_table(folder / f"notinject/data/NotInject_{tier}-00000-of-00001.parquet").to_pylist()
        for index, row in enumerate(raw):
            if not isinstance(row["prompt"], str) or not row["prompt"].strip():
                raise ValueError("Empty NotInject prompt")
            rows.append({"id": f"notinject-{tier}-{index:03}", "source": "notinject", "task": None,
                         "content": row["prompt"], "label": 0, "group_id": tier,
                         "split": "external", "role": "standalone_benign_prompt"})
    return rows, {"injecagent_exact_duplicates_removed": duplicates,
                  "injecagent": "attack recall only; clean responses unavailable, no invented benign examples",
                  "notinject": "benign FPR only; no task means no joint-model score"}


def external_overlap(reference: list[dict], candidates: list[dict]) -> list[str]:
    """Filter external items touching development contexts/bodies without scoring."""
    tasks = {canonical(r["task"]) for r in reference}
    texts = [canonical(r["content"]) for r in reference + candidates]
    matrix = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), max_features=50000,
                             dtype=np.float32).fit_transform(texts)
    excluded = []
    for start in range(0, len(candidates), 64):
        block = (matrix[len(reference) + start:len(reference) + start + 64] @ matrix[:len(reference)].T).toarray()
        for offset, scores in enumerate(block):
            row = candidates[start + offset]
            if (row["task"] is not None and canonical(row["task"]) in tasks) or scores.max() >= .88:
                excluded.append(row["id"])
    return excluded


def balanced_group_subset(rows: list[dict], target: int = 600) -> list[str]:
    """Take complete training groups until a predeclared approximate row budget."""
    if not rows or target < 1 or any(r["split"] != "train" for r in rows):
        raise ValueError("Require training-only rows and a positive target")
    selected = []
    for group in sorted({r["group_id"] for r in rows}, key=order_key):
        selected.extend(r["id"] for r in rows if r["group_id"] == group)
        if len(selected) >= target:
            break
    if len(selected) < target:
        raise ValueError("Insufficient rows for matched-size control")
    return selected
