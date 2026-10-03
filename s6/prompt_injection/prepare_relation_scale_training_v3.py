"""Freeze v3 training data, prompt and pre-registered evaluation plan before any v3 gradient step."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "data/bipia/relation_scale_training_v1"
REFERENCES = ROOT / "data/bipia/relation_scale_targets_v3"
HOLDOUT = ROOT / "data/bipia/relation_holdout_v3"
OUT = ROOT / "data/bipia/relation_scale_training_v3"

EVALUATION_PLAN = {
    "development_validation": {
        "status": "Exposed in v1; diagnostic only, never an independent claim",
        "arms": "base_zero_v3, base_fewshot_v3 (training example scale-seed-dev2-01, v3 reference), every trained v3 adapter",
        "decoding": "v3 prompt, greedy, max 1600 new tokens, 4096 total, BF16 autocast, no grammar/repair/retry/truncation",
        "scoring": "relation_contract_v3 strict units; per arm deduplicated 6 tasks + 18 contents; core and layout separate"},
    "sealed_holdout": {
        "opening_gate": "Only after development evaluation and its verification are COMPLETE; opened once; never rerun",
        "arms": "same v3 arms plus v1 large_28 adapter under its frozen v2 prompt (cross-version reference)",
        "primary": "core content exact /18, task exact /6, both sides exact /18, strict unit precision/recall",
        "secondary": "claims-excluded unit precision/recall for v1-vs-v3, contract validity, attribution categories",
        "v1_adaptation": "v2-valid output gets claims=[]; v1 cannot earn claims units, so claims-excluded metrics are reported",
        "near_domain_groups": ["object_lifecycle", "remote_branch_publish"],
        "after_opening": "No retraining, prompt change or selection on holdout results; any new method needs a new version and new holdout"},
}


def main() -> None:
    for path in (REFERENCES, HOLDOUT):
        if read_json(path / "status.json")["state"] != "COMPLETE":
            raise ValueError(f"Upstream not complete: {path}")
    v1 = read_json(V1 / "protocol.json")
    require_hash(V1 / "samples.json", read_json(V1 / "manifest.json")["samples_sha256"])
    rows = read_json(REFERENCES / "samples.json")
    if [(r["id"], r["split"], r["inputs"]) for r in rows] != [(r["id"], r["split"], r["inputs"]) for r in read_json(V1 / "samples.json")]:
        raise ValueError("v3 rows must keep v1 inputs and splits exactly")
    sources = {str(p.relative_to(ROOT)).replace("\\", "/"): file_sha256(p) for p in (
        REFERENCES / "samples.json", HOLDOUT / "samples.json", V1 / "protocol.json",
        *(ROOT / "s6/prompt_injection" / n for n in (
            "relation_contract_v3.py", "relation_sft_v3_io.py", "relation_targets_v3.py", "RELATION_CONTRACT_V3_ZH.md",
            "relation_sft_runtime.py", "prepare_relation_scale_training_v3.py")))}
    protocol = {"date": "2026-10-03", "protected_sha256": sources, "subsets": v1["subsets"],
                "training": v1["training"] + " Identical to v1 except v3 references and v3 prompt.",
                "arms_rule": "Trained arms chosen and recorded at training start, before any v3 output is seen; none added afterwards.",
                "evaluation_plan": EVALUATION_PLAN,
                "comparison_caveat": "Norms were chosen after v1 validation outputs were seen; only the sealed holdout can support an independent claim.",
                "human_labels": "Semantic labels human-reviewed; v3 machine fields assistant-derived, not field-by-field reviewed."}
    with new_run(OUT, protocol):
        write_json(OUT / "samples.json", rows)
        write_json(OUT / "manifest.json", {"samples_sha256": file_sha256(OUT / "samples.json"),
                   "train_pairs": sum(r["split"] == "train" for r in rows),
                   "validation_pairs": sum(r["split"] == "validation" for r in rows),
                   "holdout_pairs_sealed_elsewhere": len(read_json(HOLDOUT / "samples.json")), "training_started": False})
    print(f"V3 training data and evaluation plan frozen: {OUT}", flush=True)


if __name__ == "__main__":
    main()
