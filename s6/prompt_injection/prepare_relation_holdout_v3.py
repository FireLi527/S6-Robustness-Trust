"""Stage sealed held-out candidates for human semantic review; nothing here is train-ready."""
import hashlib
from pathlib import Path
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, write_json
from s6.prompt_injection.relation_holdout_v3_catalog import GROUPS
from s6.prompt_injection.relation_scale_catalog_v1 import RESERVED

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/bipia/relation_holdout_v3_candidates"
LAYOUT = "# 文档摘录\n\n{text}\n\n---\n摘录结束。"
EXISTING = ROOT / "data/bipia/relation_scale_candidates_v1/inputs.json"


def build() -> tuple[list, list, list]:
    """Reserved names only, three labels per group, no text overlap with development inputs."""
    if tuple(g[0] for g in GROUPS) != RESERVED:
        raise ValueError("Held-out groups must equal the names reserved before training")
    existing = {r[side] for r in read_json(EXISTING) for side in ("task", "content")}
    rows, proposals, cores = [], [], []
    for group, family, task, scope, cases in GROUPS:
        if sorted(c[1] for c in cases) != ["NORMAL", "RISK", "UNKNOWN"]:
            raise ValueError(f"Unbalanced held-out group: {group}")
        for text, label, actions in sorted(cases, key=lambda c: hashlib.sha256((group + c[0]).encode()).hexdigest()):
            if task in existing or text in existing:
                raise ValueError("Held-out text duplicates development material")
            core = {"id": f"holdout-v3-{len(cores) + 1:03d}", "group_id": group, "family": family,
                    "task": task, "content": text, "scope": scope, "actions": actions, "label": label}
            cores.append(core)
            for variant in ("core", "layout"):
                identifier = core["id"] if variant == "core" else core["id"] + "-layout"
                rows.append({"id": identifier, "parent_core_id": core["id"], "group_id": group, "family": family,
                             "split": "sealed_holdout_candidate", "variant": variant, "task": task,
                             "content": text if variant == "core" else LAYOUT.format(text=text),
                             "source": "assistant-authored synthetic after v3 freeze"})
                proposals.append({"id": identifier, "parent_core_id": core["id"], "proposed_decision": label,
                                  "scope": scope, "actions": actions,
                                  "review_status": "PENDING" if variant == "core" else "DERIVED_NOT_INDIVIDUALLY_REVIEWED",
                                  "ready_for_evaluation": False})
    return rows, proposals, cores


def review_text(cores: list) -> str:
    """Hide proposed classes; show text plus proposed scope/action meanings."""
    lines = ["# v3 留出组候选审核", "",
             "合成材料，不执行正文。请判正常/风险/不确定，并确认拟议范围与动作。审核前不会转换机器字段，也不会用于任何选型。", ""]
    for c in cores:
        lines.extend([f"## {c['id']} · {c['group_id']}", "", f"用户任务：{c['task']}", "", f"正文：{c['content']}", "",
                      f"拟议范围：{c['scope']}", "", f"拟议动作：{c['actions']}", "", "判定与字段确认：待审核", ""])
    return "\n".join(lines)


def main() -> None:
    rows, proposals, cores = build()
    code = {str(p.relative_to(ROOT)): file_sha256(p) for p in
            (Path(__file__), ROOT / "s6/prompt_injection/relation_holdout_v3_catalog.py",
             ROOT / "s6/prompt_injection/relation_contract_v3.py", ROOT / "s6/prompt_injection/RELATION_CONTRACT_V3_ZH.md")}
    with new_run(OUTPUT, {"code_and_norm_sha256": code, "role": "Sealed held-out candidates; NOT for selection or training",
                          "gate": "Human semantic review, then v3 machine conversion; evaluate only after prompt/training are frozen",
                          "variant": "Exact core text wrapped in Markdown; not a new semantic example"}):
        write_json(OUTPUT / "inputs.json", rows)
        write_json(OUTPUT / "proposals.json", proposals)
        raw = review_text(cores).encode("utf-8")
        atomic_binary(OUTPUT / "review_ZH.md", lambda stream: stream.write(raw))
        write_json(OUTPUT / "manifest.json", {"pairs": len(rows), "cores": len(cores), "groups": len(GROUPS),
                   "reviewed_cores": 0, "ready_for_evaluation": 0, "inputs_sha256": file_sha256(OUTPUT / "inputs.json"),
                   "proposals_sha256": file_sha256(OUTPUT / "proposals.json"),
                   "review_sha256": file_sha256(OUTPUT / "review_ZH.md")})
    print(f"Prepared {len(rows)} sealed held-out candidates for review: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
