"""Freeze v3 references for the scale materials; inputs, splits and v1 files stay unchanged."""
from collections import Counter
import copy
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, write_json
from s6.prompt_injection.relation_targets_v3 import EDITS, migrate

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "data/bipia/relation_scale_training_v1/samples.json"
EVALUATION_PROTOCOL = ROOT / "results/bipia/relation_scale_evaluation_v1/protocol.json"
OUTPUT = ROOT / "data/bipia/relation_scale_targets_v3"


def frozen_samples_hash() -> str:
    """Use the hash recorded before the v1 evaluation, not a freshly computed one."""
    for name, digest in read_json(EVALUATION_PROTOCOL)["protected_sha256"].items():
        if name.replace("\\", "/") == "data/bipia/relation_scale_training_v1/samples.json":
            if file_sha256(SAMPLES) != digest:
                raise ValueError("Frozen v1 samples changed")
            return digest
    raise ValueError("No frozen hash for v1 samples")


def build(rows: list) -> tuple[list, list]:
    """Migrate every row; log each distinct core reference once."""
    out, changes, logged, hit = [], [], set(), set()
    for row in rows:
        new = copy.deepcopy(row)
        for side in ("task", "content"):
            key = ("task", row["group_id"]) if side == "task" else ("content", row["parent_core_id"])
            target, rules = migrate(row["targets"][side], key, row["inputs"][side])
            new["targets"][side] = target
            hit.add(key)
            if row["variant"] == "core" and key not in logged:
                logged.add(key)
                changes.append({"side": side, "key": key[1], "split": row["split"], "rules": rules,
                                "changed": bool(rules), "v1": row["targets"][side], "v3": target})
        new.update(reference_version="v3", reference_provenance="v1 machine reference migrated by logged v3 rules; "
                   "semantic labels unchanged; not field-by-field human reviewed")
        out.append(new)
    unused = set(EDITS) - hit
    if unused:
        raise ValueError(f"Edits matched no reference: {sorted(unused)}")
    return out, changes


def main() -> None:
    digest = frozen_samples_hash()
    rows = read_json(SAMPLES)
    migrated, changes = build(rows)
    rule_counts = Counter(rule for c in changes for rule in set(c["rules"]))
    summary = {"core_references": len(changes), "changed_references": sum(c["changed"] for c in changes),
               "changed_validation_references": sum(c["changed"] and c["split"] == "validation" for c in changes),
               "references_touched_by_rule": dict(sorted(rule_counts.items())),
               "rows": len(migrated), "inputs_unchanged": True, "splits_unchanged": True,
               "post_hoc_note": "Norms chosen after validation outputs were seen; v3 rescoring is diagnostic only."}
    code = {name: file_sha256(ROOT / "s6/prompt_injection" / name) for name in
            ("relation_contract_v3.py", "relation_targets_v3.py", "prepare_relation_targets_v3.py")}
    with new_run(OUTPUT, {"source_samples_sha256": digest, "code_sha256": code,
                          "norms": "RELATION_CONTRACT_V3_ZH.md, user approval 2026-10-03"}) as run:
        write_json(run / "samples.json", migrated)
        write_json(run / "changes.json", changes)
        write_json(run / "summary.json", summary)
    print(f"V3 references COMPLETE: {summary['changed_references']}/{summary['core_references']} changed", flush=True)


if __name__ == "__main__":
    main()
