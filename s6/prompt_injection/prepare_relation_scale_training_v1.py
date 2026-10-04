"""Freeze approved scale references and fixed development-only training protocol."""
from pathlib import Path
from difflib import SequenceMatcher
from s6.engineering.artifacts import file_sha256, new_run, write_json
from s6.prompt_injection.relation_scale_data_v1 import build

ROOT = Path(__file__).resolve().parents[2]


def audit(rows: list) -> dict:
    """Diagnostic lexical overlap, not proof of semantic independence."""
    cores = [r for r in rows if r["variant"] == "core"]
    training = [r for r in cores if r["split"] == "train"]
    validation = [r for r in cores if r["split"] == "validation"]
    pairs = []
    for a in training:
        for b in validation:
            if any(a["inputs"][s] == b["inputs"][s] for s in ("task", "content")):
                raise ValueError("Exact cross-split input overlap")
            ratio = SequenceMatcher(None, a["inputs"]["task"] + a["inputs"]["content"], b["inputs"]["task"] + b["inputs"]["content"]).ratio()
            pairs.append({"a": a["id"], "b": b["id"], "ratio": ratio})
    return {"exact_cross_split_overlap": 0, "top_lexical_pairs": sorted(pairs, key=lambda x: -x["ratio"])[:10],
            "threshold_used_for_automatic_split": False, "same_author_synthetic": True,
            "semantic_independence_proven": False, "linked_families_kept_together": True}


def main() -> None:
    rows, subsets, protected = build()
    protected[str(Path(__file__).relative_to(ROOT))] = file_sha256(Path(__file__))
    out = ROOT / "data/bipia/relation_scale_training_v1"
    protocol = {"protected_sha256": protected, "date": "2026-10-03", "subsets": subsets,
                "selection": "Seeds8 plus SHA256 scale-order-v1 additional groups; nested8/16/28. Family-defined6 validation groups, no random row split.",
                "training": "Fresh official Qwen3-4B NF4 q/v rank8 alpha16 dropout.05 seed2026, AdamW lr2e-4 wd.01, fixed3 epochs, batch1 accumulate4, answer-only loss. No checkpoint selection.",
                "evaluation": "Same v2 prompt/strict scoring, fixed training example scale-seed-dev2-01, greedy1600 output4096 total. Development validation only. All3 adapters freeze before viewing results. Core and layout reported separately.",
                "resource": "Sequential adapters; preserve user GPU processes; reject train>2048 tokens and input+1600>4096 without truncation.",
                "scale_caveat": "Fixed epochs, not equal optimizer steps or tokens; conclusions about data exposure and compute jointly, not pure data-only effect.",
                "holdout": "Six future groups/36 cases not yet authored; this phase cannot claim independent test generalization.",
                "human_labels": "102 cores human-reviewed; machine fields assistant-derived; layout variants not individually human-reviewed; no tool permission."}
    with new_run(out, protocol):
        write_json(out / "samples.json", rows)
        write_json(out / "split_audit.json", audit(rows))
        write_json(out / "manifest.json", {"samples_sha256": file_sha256(out / "samples.json"), "core_count": 102,
                   "train_pairs": 168, "validation_pairs": 36, "independent_test_pairs": 0,
                   "subsets": {name: {"groups": len(groups), "pairs": len(groups) * 6, "semantic_cores": len(groups) * 3,
                                      "unique_training_sides": len(groups) * 7} for name, groups in subsets.items()},
                   "training_started": False, "machine_fields_human_reviewed": False})
    print(f"Scale training data frozen: {out}", flush=True)


if __name__ == "__main__":
    main()
