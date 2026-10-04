"""Strict SecOPD field mapping and versioned task/content group construction."""
from __future__ import annotations

from collections import Counter
import hashlib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from sklearn.model_selection import GroupShuffleSplit


def canonical(text: str) -> str:
    """Whitespace/case normalization for grouping only."""
    return " ".join(text.casefold().split())


def parse_pair(row: dict, index: int) -> dict:
    """Extract trusted task and carrier, verifying clean reconstruction exactly."""
    for field in ("prompt", "chosen_input", "chosen_data", "rejected_input_whole", "rejected_input"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError("missing_field")
    if type(row.get("inject_at_the_end")) is not bool:
        raise ValueError("invalid_placement")
    clean = row["chosen_data"]
    clean_suffix = "\n\n" + clean
    if not row["chosen_input"].endswith(clean_suffix):
        raise ValueError("chosen_input_boundary")
    task = row["chosen_input"][:-len(clean_suffix)]
    prefix = "<|im_start|>user\n" + task + "<|im_end|>\n<|im_start|>input\n"
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n"
    if not task.strip() or not row["prompt"].startswith(prefix) or not row["prompt"].endswith(suffix):
        raise ValueError("prompt_boundary")
    attacked = row["prompt"][len(prefix):-len(suffix)]
    injection = row["rejected_input_whole"]
    if attacked.count(injection) != 1:
        raise ValueError("injection_count")
    if attacked.replace(injection, "", 1).strip() != clean.strip():
        raise ValueError("clean_reconstruction")
    if not (attacked.endswith(injection) if row["inject_at_the_end"] else attacked.startswith(injection)):
        raise ValueError("injection_placement")
    return {"id": f"secopd-{index:05}", "source_index": index, "task": task, "clean": clean,
            "attacked": attacked, "injection": injection, "attack_seed": row["rejected_input"],
            "placement": "suffix" if row["inject_at_the_end"] else "prefix"}


def selected_pairs(raw: list[dict], count: int = 1000) -> tuple[list[dict], dict]:
    """Deterministic hash-ranked sampling after strict schema checks, no scoring."""
    valid, excluded = [], []
    for index, row in enumerate(raw):
        try:
            valid.append(parse_pair(row, index))
        except ValueError as error:
            excluded.append({"source_index": index, "reason": str(error)})
    if count < 1 or len(valid) < count:
        raise ValueError("Insufficient valid records")
    ordered = sorted(valid, key=lambda r: hashlib.sha256(f'2026:{r["source_index"]}'.encode()).hexdigest())
    return ordered[:count], {"raw_count": len(raw), "valid_count": len(valid), "selected_count": count,
                             "excluded": excluded, "exclusion_counts": dict(Counter(r["reason"] for r in excluded))}


def pair_groups(pairs: list[dict]) -> tuple[list[int], dict]:
    """Union task/clean/attack-seed/injection identities and near carrier content."""
    if not pairs or len({r["id"] for r in pairs}) != len(pairs):
        raise ValueError("Empty or duplicate pair identifiers")
    parent = list(range(len(pairs)))
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a: int, b: int) -> None:
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)
    identities, texts, owners = {}, [], []
    for i, row in enumerate(pairs):
        for field in ("task", "clean", "attacked", "attack_seed", "injection"):
            key = ("carrier" if field in {"clean", "attacked"} else field, canonical(row[field]))
            if key in identities:
                union(i, identities[key])
            else:
                identities[key] = i
        texts.extend([canonical(row["clean"]), canonical(row["attacked"])])
        owners.extend([i, i])
    matrix = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), max_features=50000,
                             dtype=np.float32).fit_transform(texts)
    cross_pair_edges = []
    for start in range(0, len(texts), 64):
        sim = linear_kernel(matrix[start:start + 64], matrix, dense_output=False).tocsr()
        for offset in range(sim.shape[0]):
            left = start + offset
            for right, value in zip(sim[offset].indices, sim[offset].data):
                if right > left and owners[left] != owners[right] and value >= .88:
                    union(owners[left], owners[right])
                    cross_pair_edges.append([owners[left], owners[right]])
    groups = [find(i) for i in range(len(pairs))]
    return groups, {"group_count": len(set(groups)), "largest_group_pairs": max(Counter(groups).values()),
                    "near_edges": cross_pair_edges, "rule": "exact task, carrier, attack seed, injection; char3-5 TFIDF50k cosine>=.88 carriers"}


def grouped_split(pairs: list[dict], groups: list[int]) -> tuple[list[dict], dict]:
    """60/20/20 group split; preview-exposed first64 source records force train."""
    if len(pairs) != len(groups) or len(set(groups)) < 10:
        raise ValueError("Insufficient independent groups for planned split")
    forced = {group for row, group in zip(pairs, groups) if row["source_index"] < 64}
    eligible = np.array([i for i, group in enumerate(groups) if group not in forced])
    if len({groups[i] for i in eligible}) < 10:
        raise ValueError("Insufficient unexposed groups")
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=2026).split(eligible, groups=np.array(groups)[eligible]))
    rest = eligible[trainval]
    train, validation = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=2026).split(rest, groups=np.array(groups)[rest]))
    assignment = {int(i): "train" for i in rest[train]}
    assignment.update({int(i): "validation" for i in rest[validation]})
    assignment.update({int(i): "test" for i in eligible[test]})
    assignment.update({i: "train" for i, group in enumerate(groups) if group in forced})
    rows = [{**r, "group_id": int(g), "split": assignment[i]} for i, (r, g) in enumerate(zip(pairs, groups))]
    counts = Counter(r["split"] for r in rows)
    if counts["validation"] < 80 or counts["test"] < 80 or counts["train"] < 200:
        raise ValueError("Fixed split below minimum sizes; no seed retry")
    return rows, {"pair_counts": dict(counts), "forced_train_groups": sorted(forced)}


def small_training_ids(pairs: list[dict], target: int = 100) -> list[str]:
    """Take complete training groups in fixed hash order until target pairs reached."""
    groups = sorted({r["group_id"] for r in pairs if r["split"] == "train"},
                    key=lambda g: hashlib.sha256(f"small2026:{g}".encode()).hexdigest())
    selected = []
    for group in groups:
        selected.extend(r["id"] for r in pairs if r["split"] == "train" and r["group_id"] == group)
        if len(selected) >= target:
            return selected
    raise ValueError("Not enough training pairs")
