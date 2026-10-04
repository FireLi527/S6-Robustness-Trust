"""Audited input assembly for document aggregation research; never invent tasks."""
from __future__ import annotations

import json
from pathlib import Path

from s6.engineering.artifacts import read_json, require_hash


def native_development(root: Path) -> list[dict]:
    """Return only original train/validation rows after integrity/group checks."""
    folder = root / "data/bipia/native_pairs_v1"
    protocol = read_json(folder / "protocol.json")
    require_hash(folder / "samples.json", protocol["samples_sha256"])
    all_rows = read_json(folder / "samples.json")
    rows = [row for row in all_rows if row["split"] in {"train", "validation"}]
    groups = {split: {r["group_id"] for r in all_rows if r["split"] == split}
              for split in ("train", "validation", "test")}
    if any(groups[a] & groups[b] for a,b in (("train","validation"),("train","test"),("validation","test"))):
        raise ValueError("Group leakage in native source")
    if len(rows) != 118 or sum(r["split"] == "train" for r in rows) != 89:
        raise ValueError("Unexpected native development split")
    return rows


def reviewed_pairs(root: Path) -> list[dict]:
    """Resolve human decisions over candidate labels for seen diagnostics."""
    folder = root / "data/bipia/repo_file_v2"
    review = read_json(folder / "human_review_completion.json")
    rows = []
    for batch in ("batch1", "batch2"):
        path = folder / f"candidate_{batch}.json"
        require_hash(path, review[batch]["candidate_sha256"])
        benign, attacks = set(review[batch]["benign"]), set(review[batch]["injection"])
        source = read_json(path)["samples"]
        if benign & attacks or benign | attacks != {r["review_number"] for r in source}:
            raise ValueError("Incomplete reviewed labels")
        rows.extend({"id": r["sample_id"], "task": r["user_task"], "content": r["content"],
                     "label": int(r["review_number"] in attacks), "group_id": r["split_group"],
                     "split": "seen_diagnostic"} for r in source)
    if len(rows) != 36:
        raise ValueError("Unexpected reviewed pair count")
    return rows


def reviewed_maintenance(root: Path) -> list[dict]:
    """Load reviewed benign excerpts without inventing missing user tasks."""
    review = read_json(root / "data/bipia/repo_file_review_v1/human_review_final.json")
    path = root / review["source_samples"]
    require_hash(path, review["source_samples_sha256"])
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 30 or any(review["labels_by_sample_number"].get(str(i)) != "benign_content"
                              for i in range(1, len(rows) + 1)):
        raise ValueError("Maintenance labels are incomplete")
    markers = ("::", "```", ">>>", "pytest ", "python ", "pip ", "tox", "git ")
    return [{"id": r["source_id"], "content": r["content"], "repo": r["repo"], "label": 0,
             "has_command_marker": any(marker in r["content"].lower() for marker in markers),
             "split": "seen_diagnostic", "task": None} for r in rows]


def maintenance_stress(rows: list[dict], tokenizer, minimum_tokens: int = 768) -> list[dict]:
    """Three derived fixtures, not new independent examples or a population FPR set."""
    if minimum_tokens < 1:
        raise ValueError("Minimum fixture length must be positive")
    fixtures = []
    for repo in sorted({r["repo"] for r in rows}):
        members = [r for r in rows if r["repo"] == repo]
        base = "\n\n".join(r["content"] for r in members)
        if not tokenizer.encode(base, add_special_tokens=False, truncation=False):
            raise ValueError("Cannot extend empty maintenance content")
        body = base
        repeats = 1
        while len(tokenizer.encode(body, add_special_tokens=False, truncation=False)) < minimum_tokens:
            repeats += 1
            body = "\n\n".join([base] * repeats)
        fixtures.append({"id": f"derived-long-{repo}", "content": body, "task": None,
                         "label": 0, "repo": repo, "source_ids": [r["id"] for r in members],
                         "repetitions": repeats, "split": "derived_stress",
                         "label_basis": "concatenation/repetition of already reviewed benign excerpts; not newly reviewed"})
    return fixtures
