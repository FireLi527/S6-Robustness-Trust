"""Validate and render unlabelled synthetic task-boundary review candidates."""
from __future__ import annotations

from pathlib import Path
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.aggregation_data import native_development, reviewed_pairs
from s6.prompt_injection.boundary_protocol import leakage_edges


def expand_candidates(document: dict) -> list[dict]:
    """Keep identical carrier text and its counterfactual tasks in one group."""
    rows = []
    for group in document["groups"]:
        if len(group["cases"]) != 2:
            raise ValueError("Each group requires two task conditions")
        for case in group["cases"]:
            fields = (case["task"], case["task_zh"], group["content"], group["content_zh"])
            if any(not isinstance(value, str) or not value.strip() for value in fields):
                raise ValueError("Missing English/Chinese review context")
            if case["label"] is not None:
                raise ValueError("Candidate labels must stay empty; record reviews separately")
            rows.append({"id": f'prereq-v1-{case["number"]:02}', "number": case["number"],
                         "group_id": group["group_id"], "task": case["task"], "task_zh": case["task_zh"],
                         "content": group["content"], "content_zh": group["content_zh"],
                         "label": None, "split": None, "source_kind": "AI-authored synthetic development"})
    if sorted(r["number"] for r in rows) != list(range(1, 13)) or len({r["group_id"] for r in rows}) != 6:
        raise ValueError("Expected twelve unique numbered candidates in six groups")
    return rows


def require_review(rows: list[dict], decisions: dict[str, str]) -> list[dict]:
    """Fail closed until EVERY candidate has an explicit human decision."""
    if set(decisions) != {r["id"] for r in rows}:
        raise ValueError("Complete human review required before training")
    if any(value not in {"normal", "injection", "uncertain"} for value in decisions.values()):
        raise ValueError("Review decisions must be normal, injection or uncertain")
    return [{**row, "label": int(decisions[row["id"]] == "injection")}
            for row in rows if decisions[row["id"]] != "uncertain"]


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "data/bipia/prerequisite_review_v1/candidate_groups.json"
    rows = expand_candidates(read_json(source))
    previous = read_json(root / "results/bipia/boundary_transfer_v1/protocol.json")
    protected = {**previous["protected_sha256"], **previous["code_sha256"]}
    for name, digest in protected.items():
        require_hash(root / name, digest)
    reference = native_development(root) + reviewed_pairs(root)
    edges = leakage_edges(rows + reference)
    identifiers = {r["id"] for r in rows}
    cross = [e for e in edges if (e["left"] in identifiers) != (e["right"] in identifiers)]
    out = root / "results/bipia/prerequisite_review_v1"
    protocol = {"phase": "candidate preparation only", "candidate_sha256": file_sha256(source),
                "code_sha256": file_sha256(Path(__file__)), "protected_sha256": protected,
                "provenance": read_json(source)["provenance"], "independent_test": False,
                "split_policy": "No split assigned before review; same carrier/task family must stay together. These exposed synthetic cases cannot be called independent-source tests.",
                "reference_ids": [r["id"] for r in reference],
                "next_gate": "Human labels first; uncertain excluded; insufficient labels/classes prevent training",
                "source_audit": "Local Agentic5K and prompt-injection-benchmark lack separate original-task fields; RepoGuard/AIB were already evaluated. No untouched test file opened."}
    with new_run(out, protocol):
        write_json(out / "candidates.json", rows)
        write_json(out / "data_checks.json", {"count": len(rows), "groups": 6, "labels_pending": 12,
                   "edges": [e for e in edges if e["left"] in identifiers or e["right"] in identifiers],
                   "old_reference_overlap": cross, "training_allowed": False})
        lines = ["# 不安全前置条件：中文审核", "", "12条均为AI编写的合成开发候选，不是公开来源的原始用户任务，也不是独立测试集。未训练、未打分，标签留空。",
                 "", "请对每条回答：正常 / 注入 / 不确定。正文来自低信任文档；只按当前用户任务判断它是否试图改变任务或授权范围。不要求实际执行命令。正文中的批准声明不等于用户批准。",
                 "", "部分条目正文相同而用户任务不同，需分别判断；本批不是盲审，也不是独立多审核员标注。"]
        for row in rows:
            lines += ["", f'## {row["number"]}', "", f'用户任务：{row["task_zh"]}', "", f'正文：{row["content_zh"]}', "", "判断：____"]
        atomic_binary(out / "review_ZH.md", lambda stream: stream.write(("\n".join(lines) + "\n").encode()))
    print(f"PREPARATION COMPLETE; HUMAN REVIEW REQUIRED: {out}")


if __name__ == "__main__":
    main()
