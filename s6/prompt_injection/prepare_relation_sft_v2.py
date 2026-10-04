"""Freeze reviewed development groups and derived v2 fields without test reuse."""
import hashlib
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_conversion_v2 import convert

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/bipia/relation_development_review_v2"


def build() -> tuple[list[dict], dict]:
    """Require complete human meaning review; machine fields stay derived."""
    review = read_json(SOURCE / "human_review.json")
    for filename, key in (("inputs.json", "input_sha256"), ("assistant_proposals.json", "proposal_sha256")):
        require_hash(SOURCE / filename, review[key])
    inputs = read_json(SOURCE / "inputs.json")
    ids = {r["id"] for r in inputs}
    labeled = [(i, label) for label, members in review["human_decisions"].items() for i in members]
    if not review["review_complete"] or len(labeled) != len(ids) or {i for i, _ in labeled} != ids:
        raise ValueError("Incomplete or duplicated class review")
    if set(review["scope_approved_ids"]) != ids or set(review["actions_approved_ids"]) != ids:
        raise ValueError("Incomplete semantic field review")
    labels = dict(labeled)
    groups = sorted({r["group_id"] for r in inputs}, key=lambda x: hashlib.sha256(("dev2-split:" + x).encode()).hexdigest())
    rows = [{"id": r["id"], "group_id": r["group_id"],
             "split": "train" if groups.index(r["group_id"]) < 6 else "validation",
             "inputs": {side: r[side] for side in ("task", "content")}, "targets": convert(r),
             "human_decision": labels[r["id"]], "provenance": "Reviewed synthetic development; assistant-derived machine fields"} for r in inputs]
    old = read_json(ROOT / "data/bipia/relation_sft_v1/samples.json")
    old_texts = {r["inputs"][side] for r in old for side in ("task", "content")}
    if any(r["inputs"][side] in old_texts for r in rows for side in ("task", "content")):
        raise ValueError("Exact overlap with v1; explicit review required")
    paths = [SOURCE / name for name in ("inputs.json", "assistant_proposals.json", "human_review.json")]
    paths += [ROOT / "s6/prompt_injection" / name for name in
              ("RELATION_ANNOTATION_V2_ZH.md", "relation_contract_v2.py", "relation_conversion_v2.py", "prepare_relation_sft_v2.py")]
    return rows, {str(p.relative_to(ROOT)): file_sha256(p) for p in paths}


def main() -> None:
    rows, protected = build()
    out = ROOT / "data/bipia/relation_sft_v2"
    with new_run(out, {"protected_sha256": protected, "data_role": "Development only; no independent test in this run",
                       "split": "8 reviewed groups; SHA256 dev2-split ordering, first6 train, last2 validation",
                       "plan": "Same official NF4 Qwen3-4B, fresh rank8 q/v LoRA, seed2026, lr2e-4 wd.01, fixed3 epochs, batch1 accumulate4. No selection. Compare base zero, base train-only few-shot and adapter zero. No v1 evaluation inputs. No tools.",
                       "metrics": "Strict grounded reference units; no automated semantic equivalence claim, no attack detection metrics",
                       "limitations": "Synthetic same-author groups; related boundary concepts remain; no source independence or exact v1/v2 effect comparison"}):
        write_json(out / "samples.json", rows)
        write_json(out / "manifest.json", {"samples_sha256": file_sha256(out / "samples.json"), "human_meaning_approved": 24,
                   "machine_fields_individually_human_reviewed": False, "train_pairs": 18, "validation_pairs": 6,
                   "independent_test_pairs": 0, "training_started": False})
    print(f"Prepared v2 development data: {out}", flush=True)


if __name__ == "__main__":
    main()
