"""Human-review gates, explicit conversion and family-isolated scale subsets."""
import copy
import hashlib
from pathlib import Path
from s6.engineering.artifacts import file_sha256, read_json, require_hash
from s6.prompt_injection.relation_contract_v2 import validate
from s6.prompt_injection.relation_conversion_v2 import convert as convert_seed
from s6.prompt_injection.relation_scale_targets_v1 import TASKS, TASK_CONSTRAINTS, CONTENTS, CONSTRAINTS, MISSING

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/bipia/relation_scale_candidates_v1"
VALIDATION = {"transaction_rollback", "retention_cutoff", "row_scope", "column_projection", "cache_namespace", "recipient_scope"}
FAMILIES = {
 "data_selection": {"retention_cutoff", "row_scope", "column_projection", "cache_namespace"},
 "indirection": {"seed-symlink_copy", "symlink_listing"},
 "conditional_gate": {"overwrite_precondition", "download_checksum", "backup_restore_gate", "time_window", "redaction_before_send"},
 "tool_side_effects": {"seed-patch_preview", "dry_run_dependency", "queue_ack", "review_not_approve"},
 "network_boundary": {"seed-offline_request_example", "dependency_source", "artifact_publish"},
 "resource_bounds": {"seed-container_quota", "bounded_retry", "rate_budget"},
}


def approved_labels() -> tuple[dict, dict]:
    """Require exact review coverage; never promote assistant proposals to labels."""
    labels, protected = {}, {}
    manifest = read_json(SOURCE / "manifest.json")
    for name, key in (("inputs.json", "inputs_sha256"), ("proposals.json", "proposals_sha256")):
        require_hash(SOURCE / name, manifest[key])
        protected[str((SOURCE / name).relative_to(ROOT))] = manifest[key]
    for batch, start, stop in ((1, 1, 22), (2, 22, 43), (3, 43, 61), (4, 61, 79)):
        path = SOURCE / f"human_review_{batch:02d}.json"
        review = read_json(path)
        expected = {f"scale-core-{i:03d}" for i in range(start, stop)}
        entries = [(i, label) for label, ids in review["human_decisions"].items() for i in ids]
        if not review["batch_review_complete"] or len(entries) != len(expected) or {i for i, _ in entries} != expected:
            raise ValueError("Review coverage mismatch")
        for field in ("scope_approved_ids", "actions_approved_ids"):
            if set(review[field]) != expected:
                raise ValueError("Incomplete semantic approval")
        require_hash(SOURCE / "inputs.json", review["inputs_sha256"])
        require_hash(SOURCE / "proposals.json", review["proposals_sha256"])
        require_hash(SOURCE / review["review_file"], review["review_sha256"])
        labels.update(entries)
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    seed_dir = ROOT / "data/bipia/relation_development_review_v2"
    seed = read_json(seed_dir / "human_review.json")
    require_hash(seed_dir / "inputs.json", seed["input_sha256"])
    seed_ids = {f"dev2-{i:02d}" for i in range(1, 25)}
    if not seed["review_complete"] or set(seed["scope_approved_ids"]) != seed_ids or set(seed["actions_approved_ids"]) != seed_ids:
        raise ValueError("Seed semantic approval incomplete")
    entries = [("scale-seed-" + i, label) for label, ids in seed["human_decisions"].items() for i in ids]
    if len(entries) != 24 or {i.removeprefix("scale-seed-") for i, _ in entries} != seed_ids:
        raise ValueError("Seed labels incomplete")
    labels.update(entries)
    for path in (seed_dir / "inputs.json", seed_dir / "human_review.json"):
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    return labels, protected


def convert_core(row: dict) -> dict:
    """Do not use labels or another side to resolve missing source information."""
    if row["seed_id"] is not None:
        return convert_seed({**row, "id": row["seed_id"], "group_id": row["group_id"].removeprefix("seed-")})
    number, group = int(row["id"][-3:]), row["group_id"]
    result = {}
    for side, specs, constraints, missing in (
        ("task", TASKS[group], TASK_CONSTRAINTS.get(group, []), []),
        ("content", CONTENTS[number], CONSTRAINTS.get(number, []), [MISSING[number]] if number in MISSING else [])):
        actions = [dict(copy.deepcopy(spec), evidence=row[side]) for spec in specs]
        result[side] = {"actions": actions, "constraints": list(constraints), "missing_context": list(missing)}
        validate(result[side], row[side])
    return result


def build() -> tuple[list, dict, dict]:
    """Keep parents/variants together and all exposed seeds in development train."""
    labels, protected = approved_labels()
    inputs = read_json(SOURCE / "inputs.json")
    cores = {r["id"]: r for r in inputs if r["variant"] == "core"}
    if set(labels) != set(cores) or len(inputs) != 204:
        raise ValueError("Core approval or candidate count mismatch")
    targets = {i: convert_core(r) for i, r in cores.items()}
    groups = {r["group_id"] for r in inputs}
    train_groups = groups - VALIDATION
    seeds = sorted(g for g in train_groups if g.startswith("seed-"))
    extra = sorted(train_groups - set(seeds), key=lambda g: hashlib.sha256(("scale-order-v1:" + g).encode()).hexdigest())
    subsets = {"small_8": seeds, "medium_16": seeds + extra[:8], "large_28": seeds + extra}
    family_lookup = {g: family for family, members in FAMILIES.items() for g in members}
    rows = []
    for row in inputs:
        parent = cores[row["parent_core_id"]]
        if row["group_id"] != parent["group_id"] or row["task"] != parent["task"]:
            raise ValueError("Variant group/task mismatch")
        if row["variant"] == "layout" and row["content"] != "# 文档摘录\n\n" + parent["content"] + "\n\n---\n摘录结束。":
            raise ValueError("Unexpected semantic change in derived variant")
        converted = copy.deepcopy(targets[parent["id"]])
        for side in ("task", "content"):
            validate(converted[side], row[side])
        rows.append({"id": row["id"], "parent_core_id": parent["id"], "variant": row["variant"],
                     "group_id": row["group_id"], "family": family_lookup.get(row["group_id"], row["group_id"]),
                     "split": "validation" if row["group_id"] in VALIDATION else "train",
                     "inputs": {s: row[s] for s in ("task", "content")}, "targets": converted,
                     "human_decision": labels[parent["id"]], "machine_fields_human_reviewed": False,
                     "meaning_provenance": "human-approved core" if row["variant"] == "core" else "exact-text layout derivative, not individually human reviewed"})
    for family in {r["family"] for r in rows}:
        if len({r["split"] for r in rows if r["family"] == family}) != 1:
            raise ValueError("Linked-family leakage")
    if len(train_groups) != 28 or len(groups) != 34 or len(seeds) != 8:
        raise ValueError("Unexpected group counts")
    for name in ("relation_scale_data_v1.py", "relation_scale_targets_v1.py", "relation_contract_v2.py", "relation_conversion_v2.py"):
        path = ROOT / "s6/prompt_injection" / name
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    return rows, subsets, protected
