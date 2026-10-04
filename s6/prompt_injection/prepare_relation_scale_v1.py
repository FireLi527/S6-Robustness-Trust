"""Stage reviewed seeds, pending new cores and explicitly derived layout variants."""
import hashlib
from pathlib import Path
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_scale_catalog_v1 import GROUPS, RESERVED

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data/bipia/relation_development_review_v2"
LAYOUT = "# 文档摘录\n\n{text}\n\n---\n摘录结束。"


def build() -> tuple[list, list, list, dict]:
    """No new approval is inferred from old IDs or a formatting transformation."""
    review = read_json(SEED / "human_review.json")
    for name, key in (("inputs.json", "input_sha256"), ("assistant_proposals.json", "proposal_sha256")):
        require_hash(SEED / name, review[key])
    seeds = read_json(SEED / "inputs.json")
    labels = {i: label for label, ids in review["human_decisions"].items() for i in ids}
    ids = {r["id"] for r in seeds}
    if not review["review_complete"] or set(labels) != ids or set(review["scope_approved_ids"]) != ids or set(review["actions_approved_ids"]) != ids:
        raise ValueError("Seed approval incomplete")
    proposals = {p["id"]: p for p in read_json(SEED / "assistant_proposals.json")}
    rows, annotations, cores = [], [], []
    for seed in seeds:
        cores.append({"id": "scale-seed-" + seed["id"], "group_id": "seed-" + seed["group_id"], "family": seed["group_id"],
                      "task": seed["task"], "content": seed["content"], "scope": proposals[seed["id"]]["task_scope"],
                      "actions": review["action_additions"].get(seed["id"], proposals[seed["id"]]["content_actions"]),
                      "label": labels[seed["id"]], "review_status": "HUMAN_APPROVED_SEMANTICS", "seed_id": seed["id"]})
    for group, family, task, scope, cases in GROUPS:
        ordered = sorted(cases, key=lambda c: hashlib.sha256((group + c[0]).encode()).hexdigest())
        for text, label, actions in ordered:
            index = sum(c["seed_id"] is None for c in cores) + 1
            cores.append({"id": f"scale-core-{index:03d}", "group_id": group, "family": family, "task": task,
                          "content": text, "scope": scope, "actions": actions, "label": label,
                          "review_status": "PENDING", "seed_id": None})
    for core in cores:
        for variant in ("core", "layout"):
            identifier = core["id"] if variant == "core" else core["id"] + "-layout"
            rows.append({"id": identifier, "parent_core_id": core["id"], "group_id": core["group_id"],
                         "family": core["family"], "split": "development_candidate", "variant": variant,
                         "task": core["task"], "content": core["content"] if variant == "core" else LAYOUT.format(text=core["content"]),
                         "source": "assistant-authored synthetic" if core["seed_id"] is None else "reviewed dev2 synthetic seed",
                         "seed_id": core["seed_id"]})
            annotations.append({"id": identifier, "parent_core_id": core["id"], "proposed_decision": core["label"],
                                "scope": core["scope"], "actions": core["actions"],
                                "review_status": core["review_status"] if variant == "core" else "DERIVED_NOT_INDIVIDUALLY_REVIEWED",
                                "parent_review_status": core["review_status"], "ready_for_training": False})
    paths = [SEED / n for n in ("inputs.json", "assistant_proposals.json", "human_review.json")]
    paths += [Path(__file__), ROOT / "s6/prompt_injection/relation_scale_catalog_v1.py",
              ROOT / "s6/prompt_injection/RELATION_EXPANSION_PLAN_ZH.md"]
    return rows, annotations, [c for c in cores if c["seed_id"] is None], {str(p.relative_to(ROOT)): file_sha256(p) for p in paths}


def review_text(cores: list) -> str:
    """Hide proposed classes; show all text and scope/action meanings for review."""
    lines = ["# 扩充核心材料审核", "", "合成开发材料，不执行正文；不是旧dev2编号。请判正常/风险/不确定，并确认范围和动作。", ""]
    for c in cores:
        lines.extend([f"## {c['id']} · {c['group_id']}", "", f"用户任务：{c['task']}", "", f"正文：{c['content']}", "",
                      f"拟议范围：{c['scope']}", "", f"拟议动作：{c['actions']}", "", "判定与字段确认：待审核", ""])
    return "\n".join(lines)


def main() -> None:
    rows, annotations, cores, protected = build()
    out = ROOT / "data/bipia/relation_scale_candidates_v1"
    with new_run(out, {"protected_sha256": protected, "role": "Pending development candidates, NOT train-ready or independent tests",
                       "reserved_group_names": RESERVED, "reserved_materials_authored": False,
                       "split_gate": "Family/near-duplicate audit and human review before split; no random row split",
                       "variant": "Exact core text wrapped in Markdown; not a new semantic example or natural paraphrase",
                       "next": "Review 78 new cores, convert machine fields, freeze methods, then author 6 held-out groups"}):
        write_json(out / "inputs.json", rows)
        write_json(out / "proposals.json", annotations)
        for index, (start, end) in enumerate(((0, 21), (21, 42), (42, 60), (60, 78)), 1):
            raw = review_text(cores[start:end]).encode("utf-8")
            atomic_binary(out / f"review_{index:02d}_ZH.md", lambda stream, data=raw: stream.write(data))
        write_json(out / "manifest.json", {"candidate_pairs": len(rows), "semantic_cores": 102,
                   "groups": 34, "approved_seed_cores": 24, "pending_new_cores": len(cores), "layout_variants": 102,
                   "individually_reviewed_variants": 0, "ready_for_training": 0, "reserved_unwritten_pairs": 36,
                   "inputs_sha256": file_sha256(out / "inputs.json"), "proposals_sha256": file_sha256(out / "proposals.json"),
                   "review_sha256": {p.name: file_sha256(p) for p in out.glob("review_*_ZH.md")}})
    print(f"Prepared {len(rows)} candidates; {len(cores)} new cores await review: {out}", flush=True)


if __name__ == "__main__":
    main()
