"""Freeze candidate-only defense manifests without reading scoring truth."""
from __future__ import annotations
import csv
import hashlib
import json
import random
from pathlib import Path
from dataset_config import DATA_ROOT, RESULTS_ROOT, MANIFEST_ROOT, evaluation_matches
from manifest_protocol import CANDIDATE_FIELDS, load_candidate_manifest, index_unique

DEFENSE_ROOT = DATA_ROOT / "defense"
DATASETS = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")
REMOVAL_SEED = 32026
POLICY = "Keep ALLOW only. Withhold REVIEW and QUARANTINE pending review; no relabeling."


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_rows(rows, predictions, seed):
    indexed = index_unique(rows, source="candidate input")
    if set(indexed) != set(predictions):
        raise ValueError("Prediction IDs do not match candidate IDs")
    if any(p.get("decision") not in {"ALLOW", "REVIEW", "QUARANTINE"} for p in predictions.values()):
        raise ValueError("Unknown detector decision")
    removed = {sid for sid, p in predictions.items() if p["decision"] != "ALLOW"}
    random_removed = set(random.Random(seed).sample(sorted(indexed), len(removed)))
    return {
        "semantic": ([row for row in rows if row["sample_id"] not in removed], sorted(removed)),
        "random": ([row for row in rows if row["sample_id"] not in random_removed], sorted(random_removed)),
    }


def main():
    source = RESULTS_ROOT / "semantic_sample_results.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not evaluation_matches(payload):
        raise ValueError("Frozen detector results do not match current detector/manifests")
    plan = {"policy": POLICY, "removal_seed": REMOVAL_SEED,
            "detector": payload["detector"], "prediction_file_sha256": sha(source),
            "training_seed": 2026, "epochs": 20,
            "note": "Single seed; fixed inherited detector thresholds. Random control matches total removed count, not class distribution. No hidden truth used for selection.",
            "variants": {}}
    outputs = {}
    for i, dataset in enumerate(DATASETS):
        rows = load_candidate_manifest(MANIFEST_ROOT / f"{dataset}.csv")
        selected = select_rows(rows, payload["datasets"][dataset], REMOVAL_SEED + i)
        for strategy, (kept, removed) in selected.items():
            if not kept or {row["assigned_label"] for row in kept} != {row["assigned_label"] for row in rows}:
                raise ValueError("Selection removed all samples or an entire class")
            name = f"{dataset}__{strategy}"
            outputs[name] = kept
            plan["variants"][name] = {"source_dataset": dataset, "strategy": strategy,
                "source_manifest_sha256": sha(MANIFEST_ROOT / f"{dataset}.csv"),
                "original_samples": len(rows), "retained_samples": len(kept),
                "removed_count": len(removed), "removed_sample_ids": removed}
    manifest_dir = DEFENSE_ROOT / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in outputs.items():
        path = manifest_dir / f"{name}.csv"
        import io
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader(); writer.writerows(rows)
        content = buffer.getvalue().encode("utf-8-sig")
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite a different frozen manifest: {path}")
        path.write_bytes(content)
        plan["variants"][name]["manifest_sha256"] = sha(path)
    plan_path = DEFENSE_ROOT / "selection_plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError("Refusing to overwrite a different frozen selection plan")
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({name: {k:v for k,v in data.items() if k != "removed_sample_ids"}
                     for name,data in plan["variants"].items()}, indent=2))


if __name__ == "__main__":
    main()
