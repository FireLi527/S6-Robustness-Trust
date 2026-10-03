"""Freeze sealed held-out v3 references; refuses to run before full human semantic approval."""
import copy
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_contract_v3 import validate
from s6.prompt_injection.relation_holdout_v3_targets import CLAIMS, CONSTRAINTS, CONTENTS, MISSING, TASK_CONSTRAINTS, TASKS

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/bipia/relation_holdout_v3_candidates"
OUTPUT = ROOT / "data/bipia/relation_holdout_v3"


def approved_labels(review: dict, cores: set) -> dict:
    """Labels, scope and actions must all be approved for exactly the staged cores."""
    for name, key in (("inputs.json", "inputs_sha256"), ("proposals.json", "proposals_sha256"), ("review_ZH.md", "review_sha256")):
        require_hash(SOURCE / name, review[key])
    labels = {i: label for label, ids in review["human_decisions"].items() for i in ids}
    if not review["batch_review_complete"] or set(labels) != cores or len(labels) != sum(map(len, review["human_decisions"].values())):
        raise ValueError("Held-out review incomplete")
    for field in ("scope_approved_ids", "actions_approved_ids"):
        if set(review[field]) != cores:
            raise ValueError(f"Held-out {field} incomplete")
    return labels


def target(specs: list, constraints: list, claims: list, missing: list, text: str) -> dict:
    value = {"actions": [dict(copy.deepcopy(s), evidence=text) for s in specs], "constraints": list(constraints),
             "claims": list(claims), "missing_context": list(missing)}
    validate(value, text)
    return value


def build(rows: list, labels: dict) -> list:
    """Layout rows reuse the parent reference, validated against their own wrapped text."""
    out = []
    for row in rows:
        parent, group = row["parent_core_id"], row["group_id"]
        out.append({"id": row["id"], "parent_core_id": parent, "variant": row["variant"], "group_id": group,
                    "family": row["family"], "split": "sealed_holdout",
                    "inputs": {"task": row["task"], "content": row["content"]},
                    "targets": {"task": target(TASKS[group], TASK_CONSTRAINTS.get(group, []), [], [], row["task"]),
                                "content": target(CONTENTS[parent], CONSTRAINTS.get(parent, []), CLAIMS.get(parent, []),
                                                  MISSING.get(parent, []), row["content"])},
                    "human_decision": labels[parent], "machine_fields_human_reviewed": False,
                    "reference_version": "v3"})
    return out


def main() -> None:
    rows = read_json(SOURCE / "inputs.json")
    cores = {r["id"] for r in rows if r["variant"] == "core"}
    if set(CONTENTS) != cores or {r["group_id"] for r in rows} != set(TASKS):
        raise ValueError("Reference coverage mismatch")
    labels = approved_labels(read_json(SOURCE / "human_review.json"), cores)
    samples = build(rows, labels)
    code = {name: file_sha256(ROOT / "s6/prompt_injection" / name) for name in
            ("relation_holdout_v3_targets.py", "prepare_relation_holdout_v3_targets.py", "relation_contract_v3.py")}
    with new_run(OUTPUT, {"code_sha256": code, "review_sha256": file_sha256(SOURCE / "human_review.json"),
                          "role": "SEALED independent test; never for selection, training or prompt design",
                          "gate": "Open only after v3 prompt and training configuration are frozen"}):
        write_json(OUTPUT / "samples.json", samples)
    print(f"Sealed {len(samples)} held-out v3 samples: {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
