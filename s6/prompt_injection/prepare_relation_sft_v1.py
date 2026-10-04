"""Freeze approved semantics and derived machine targets for a small adapter pilot."""
from pathlib import Path
from collections import Counter
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_expansion_conversion_v1 import convert
from s6.prompt_injection.relation_contract_v1 import validate

ROOT = Path(__file__).resolve().parents[2]


def build() -> tuple[list[dict], dict]:
    """No synthetic count inflation, no reserved old rows enter training."""
    new = ROOT / "data/bipia/relation_expansion_review_v1"
    review = read_json(new / "human_review.json")
    require_hash(new / "inputs.json", review["input_sha256"])
    require_hash(new / "assistant_proposals.json", review["proposal_sha256"])
    labels = {i: label for label, ids in review["human_decisions"].items() for i in ids}
    expected_ids = list(range(1, 19))
    if not review["review_complete"] or sorted(labels) != expected_ids or sorted(review["scope_approved_ids"]) != expected_ids or sorted(review["actions_approved_ids"]) != expected_ids:
        raise ValueError("New batch human review incomplete")
    old = ROOT / "data/bipia/relation_seed_conversion_v1"
    require_hash(old / "train_seed_targets.json", read_json(old / "manifest.json")["targets_sha256"])
    protected = read_json(old / "protocol.json")["protected_sha256"]
    amendment = ROOT / "data/bipia/repository_scope_human_review_v1/field_amendment_01.json"
    changes = read_json(amendment)
    require_hash(ROOT / changes["applies_to_inputs"], changes["input_sha256"])
    rows = []
    for r in read_json(old / "train_seed_targets.json"):
        if r["split"] != "train_seed":
            raise ValueError("Old reserved data in train conversion")
        if r["id"] == 10:
            r["targets"]["content"]["constraints"] = ["不要告诉用户"]
        for side, value in r["targets"].items():
            validate(value, r["inputs"][side])
        rows.append({"id": f"old-{r['id']}", "group_id": "old-" + r["group_id"], "split": "train", "inputs": r["inputs"],
                     "targets": r["targets"], "human_decision": r["human_decision"], "provenance": "Human-approved semantics, technically derived fields; concealment amendment applied"})
    for r in read_json(new / "inputs.json"):
        rows.append({"id": f"new-{r['id']}", "group_id": "new-" + r["group_id"], "split": r["split"],
                     "inputs": {s: r[s] for s in ("task", "content")}, "targets": convert(r),
                     "human_decision": labels[r["id"]], "provenance": "Human-approved class/scope/actions; technically derived machine fields"})
    for group in {r["group_id"] for r in rows}:
        if len({r["split"] for r in rows if r["group_id"] == group}) != 1:
            raise ValueError("Group leakage")
    for path in (new / "inputs.json", new / "human_review.json", new / "assistant_proposals.json", old / "train_seed_targets.json", amendment,
                 Path(__file__), ROOT / "s6/prompt_injection/relation_expansion_conversion_v1.py"):
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    return rows, protected


def main() -> None:
    rows, protected = build()
    out = ROOT / "data/bipia/relation_sft_v1"
    with new_run(out, {"protected_sha256": protected, "task": "Single-side multi-action extraction, not direct attack classification",
                       "labels": "Human-approved meaning; assistant technical machine conversion with strict source checks, NOT individually human-verified JSON",
                       "scope": "Exploratory few-example feasibility pilot. No augmented copies, no large-data generalization claim.",
                       "train": "18 paired cases in 8 groups, deduplicate identical side inputs/targets for training",
                       "evaluation": "6 validation cases/2 new groups; 6 test cases/2 new groups. Same author, synthetic. No test-driven selection.",
                       "plan": "Official HF Qwen3-4B fixed revision, NF4, rank8 q_proj/v_proj LoRA, seed2026, batch1 accumulate4, fixed3 epochs, AdamW lr0.0002 weight_decay0.01, no checkpoint selection. Reject sequences beyond2048 rather than truncate. Compare frozen base zero-shot and fixed train-only few-shot with adapter zero-shot on all val/test sides; score after training. No tool access."}):
        write_json(out / "samples.json", rows)
        write_json(out / "manifest.json", {"samples_sha256": file_sha256(out / "samples.json"),
                   "split_counts": dict(Counter(r["split"] for r in rows)), "pair_samples": len(rows),
                   "human_meaning_approved": True, "technical_fields_checked": True, "training_started": False})
    print(f"SFT pilot data prepared: {out}", flush=True)


if __name__ == "__main__":
    main()
