"""Schema-preserving source audit; never equate probe presence with maliciousness."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json


def text_value(value: object) -> str:
    """Reject absent task/content instead of inventing or silently stringifying it."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected an existing nonempty source string")
    return value


def normalize(text: str) -> str:
    """Canonical form used only for duplicate/group audit, not model training."""
    return " ".join(text.casefold().split())


def jsonl(path: Path) -> list[dict]:
    """Read local pinned records as data, without executable parsing."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def secfid_pairs(rows: list[dict], agentic: bool = False) -> list[dict]:
    """Expose source task/clean/input variants; leave binary risk labels UNASSIGNED."""
    output = []
    source = "secfid_agentic" if agentic else "secfid_main"
    for row in rows:
        task = text_value(row["instruction"])
        field = row["agentic"] if agentic else row["data"]
        names = ("clean_tool_response", "tool_response") if agentic else ("base", "input")
        for name, variant in zip(names, ("clean", "probe_present")):
            output.append({"id": f'{source}/{row["id"]}/{variant}', "pair_id": f'{source}/{row["id"]}',
                           "source": source, "source_id": row["id"], "task": task,
                           "content": text_value(field[name]), "clarification_question": None,
                           "variant": variant, "probe_type": row["probe"]["type"],
                           "family": row["metadata"].get("task_family", row["metadata"].get("task")),
                           "risk_label": None, "training_allowed": False,
                           "label_warning": "source evaluates executed/processed/ignored responses; no automatic malicious/normal label",
                           "source_path": f'{"agentic" if agentic else "data"}.{name}'})
    return output


def aspi_pairs(rows: list[dict]) -> list[dict]:
    """Keep clarification context and source channel, not a fabricated tool output."""
    output = []
    for index, row in enumerate(rows):
        injections = row["injections"]
        if sorted(item["operator"] for item in injections) != ["CP", "GS", "HR"]:
            raise ValueError("Unexpected ASPI operators")
        variants = [("benign", row["benign_clarification_response"])] + [
            (item["operator"], item["injected_clarification_response"]) for item in injections]
        for variant, content in variants:
            output.append({"id": f'aspi/{index}/{variant}', "pair_id": f'aspi/{index}',
                           "source": "aspi", "source_id": f'{row["suite"]}/{row["user_task_id"]}/{row["injection_task_id"]}',
                           "task_group": f'aspi/{row["suite"]}/{row["user_task_id"]}',
                           "task": text_value(row["base_prompt"]), "original_task": text_value(row["original_prompt"]),
                           "clarification_question": text_value(row["expected_clarification_question"]),
                           "content": text_value(content), "variant": variant, "family": row["suite"],
                           "risk_label": None, "source_adversarial_by_construction": variant != "benign",
                           "training_allowed": False, "channel": "clarification response, not automatically low-trust tool content",
                           "label_warning": "data card explicitly lists training as out of scope; evaluation requires source clarification/channel protocol"})
    return output


def audit_groups(rows: list[dict]) -> tuple[dict, list[int]]:
    """Union shared pair/task/content and >=.88 char-cosine near text; never split."""
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate exported IDs")
    parent = list(range(len(rows)))
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a: int, b: int) -> None:
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)
    seen, seen_text = {}, {}
    texts, representatives = [], []
    for i, row in enumerate(rows):
        content = normalize(row["content"])
        keys = [("pair", row["pair_id"]), ("task", normalize(row["task"])), ("content", content)]
        if "task_group" in row:
            keys.append(("source_task", row["task_group"]))
        for key in keys:
            if key in seen:
                union(i, seen[key])
            else:
                seen[key] = i
        if content not in seen_text:
            seen_text[content] = i
            texts.append(content)
            representatives.append(i)
    near_edges = 0
    if len(texts) > 1:
        matrix = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), max_features=50000,
                                 min_df=1, dtype=np.float32).fit_transform(texts)
        for start in range(0, len(texts), 64):
            sim = linear_kernel(matrix[start:start + 64], matrix, dense_output=False).tocsr()
            for offset in range(sim.shape[0]):
                left = start + offset
                for right, value in zip(sim[offset].indices, sim[offset].data):
                    if right > left and value >= .88:
                        union(representatives[left], representatives[right])
                        near_edges += 1
    groups = [find(i) for i in range(len(rows))]
    sizes = Counter(groups)
    identities = {(normalize(r["task"]), normalize(r.get("clarification_question") or ""), normalize(r["content"])) for r in rows}
    return {"rows": len(rows), "unique_task_context_content": len(identities), "unique_content": len(texts),
            "unique_tasks": len({normalize(r["task"]) for r in rows}), "connected_groups": len(sizes),
            "largest_group_rows": max(sizes.values(), default=0), "near_text_edges": near_edges,
            "variant_counts": dict(Counter(r["variant"] for r in rows))}, groups


def main() -> None:
    """Produce an audit-only export with no model scoring or train/test assignment."""
    root = Path(__file__).resolve().parents[2]
    source = root / "external/paired_source_audit_v1"
    manifest = read_json(source / "manifest.json")
    for name, record in manifest.items():
        require_hash(source / name, record["sha256"])
    release = read_json(source / "secfid/metadata/release_manifest.json")
    for item in release["files"]:
        if item["path"].startswith("data/"):
            require_hash(source / "secfid" / item["path"], item["sha256"])
    datasets = {"secfid_main": secfid_pairs(jsonl(source / "secfid/data/secfid.jsonl")),
                "secfid_agentic": secfid_pairs(jsonl(source / "secfid/data/secfid_agentic.jsonl"), True),
                "aspi": aspi_pairs([r for name in ("banking", "slack", "travel", "workspace")
                                     for r in jsonl(source / f"aspi/data/{name}.jsonl")])}
    out = root / "results/bipia/large_pair_source_audit_v1"
    protocol = {"source_manifest_sha256": file_sha256(source / "manifest.json"), "code_sha256": file_sha256(Path(__file__)),
                "group_rule": "shared pair, normalized task, source task ID, exact content; then char3-5 TFIDF max50k cosine>=.88 connected components",
                "use": "source audit only; all labels null; no train/calibration/test partitions; no claim of independent test",
                "exposure": "all downloaded rows inspected by schema/group audit; first example of each source also read by assistant; not a sealed test set",
                "legacy_policy": "no old datasets modified or test files opened; no model fitting/scoring"}
    with new_run(out, protocol):
        summary = {}
        for name, rows in datasets.items():
            summary[name], groups = audit_groups(rows)
            write_json(out / f"{name}_audit_only.json", [{**row, "audit_group": group, "split": None} for row, group in zip(rows, groups)])
            print(f"{name}: {summary[name]}", flush=True)
        write_json(out / "summary.json", summary)


if __name__ == "__main__":
    main()
