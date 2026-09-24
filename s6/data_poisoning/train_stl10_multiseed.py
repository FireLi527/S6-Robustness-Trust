"""Repeat the frozen 12-condition experiment; vary training seed only."""
import argparse
import json
from pathlib import Path

import torch
import train_stl10_models as trainer
from dataset_config import RESULTS_ROOT, MANIFEST_ROOT, IMAGE_ROOT
from prepare_stl10_defense import DEFENSE_ROOT, sha
from report_stl10_defense import validate_run

OUTPUT = RESULTS_ROOT / "multiseed_training"
SEEDS = (2026, 2027, 2028)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected_protocol(original, seed):
    return {**original["protocol"], "seed": seed}


def verify(summary, original, seed):
    require(summary["dataset"] == original["dataset"], "Dataset mismatch")
    require(summary["protocol"] == expected_protocol(original, seed), "Training protocol mismatch")
    require(summary["protocol_hash"] == trainer.canonical_hash({
        k: v for k, v in summary["protocol"].items() if k != "dataset"
    }), "Protocol hash mismatch")
    for key in ("trainer_sha256", "manifest_sha256", "validation_split_sha256",
                "test_split_sha256", "training_samples", "validation_samples",
                "test_samples", "pretrained_weights", "candidate_fields_only"):
        require(summary[key] == original[key], f"Frozen field changed: {key}")
    require(sha(Path(trainer.__file__)) == summary["trainer_sha256"], "Trainer changed")
    validate_run(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    baseline = read(RESULTS_ROOT / "model_training" / "comparison_summary.json")
    defense = read(RESULTS_ROOT / "defense_training" / "defense_results.json")
    plan_path = DEFENSE_ROOT / "selection_plan.json"
    plan = read(plan_path)
    require(defense["selection_plan_sha256"] == sha(plan_path), "Selection plan changed")
    originals = {s["dataset"]: s for s in baseline["summaries"] + defense["summaries"]}
    require(len(originals) == 12, "Expected all 12 original conditions")
    common = [{k: v for k, v in s["protocol"].items() if k not in ("dataset", "seed")}
              for s in originals.values()]
    require(all(p == common[0] for p in common), "Original conditions use different protocols")
    for name, s in originals.items():
        verify(s, s, 2026)
        if name in plan["variants"]:
            variant = plan["variants"][name]
            require(s["manifest_sha256"] == variant["manifest_sha256"], "Defense selection changed")
            require(originals[variant["source_dataset"]]["manifest_sha256"] ==
                    variant["source_manifest_sha256"], "Defense source changed")
    frozen = {
        "seeds": list(SEEDS), "conditions": sorted(originals), "epochs": 20,
        "selection_plan_sha256": sha(plan_path),
        "trainer_sha256": sha(Path(trainer.__file__)),
        "validation_split_sha256": sha(IMAGE_ROOT / "val.txt"),
        "test_split_sha256": sha(IMAGE_ROOT / "test.txt"),
        "manifest_sha256": {n: s["manifest_sha256"] for n, s in originals.items()},
        "common_protocol": common[0],
        "scope": "Training randomness only; fixed data split, poison instances, detector and removal selections.",
        "hidden_truth_used_for_training": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protocol_path = OUTPUT / "protocol.json"
    if protocol_path.exists():
        require(read(protocol_path) == frozen, "Frozen multiseed protocol changed")
    else:
        trainer.write_json(protocol_path, frozen)
    print("Verified original 12 runs and frozen multiseed protocol", flush=True)
    if args.verify_only:
        return
    require(torch.cuda.is_available(), "CUDA unavailable")
    summaries = list(originals.values())

    def save_progress():
        destination = OUTPUT / "progress.json"
        temporary = OUTPUT / "progress.tmp.json"
        trainer.write_json(temporary, {
            "protocol_sha256": sha(protocol_path), "wrapper_sha256": sha(Path(__file__)),
            "completed_runs": len(summaries), "expected_runs": 36, "summaries": summaries,
        })
        temporary.replace(destination)

    save_progress()
    for seed in SEEDS[1:]:
        for name, original in originals.items():
            trainer.MANIFEST_ROOT = DEFENSE_ROOT / "manifests" if name in plan["variants"] else MANIFEST_ROOT
            require(sha(trainer.MANIFEST_ROOT / f"{name}.csv") == original["manifest_sha256"], "Manifest changed")
            output = OUTPUT / f"seed{seed}"
            previous = list((output / name).glob("*/summary.json"))
            require(len(previous) <= 1, "Ambiguous previous runs")
            if previous:
                summary = read(previous[0])
                verify(summary, original, seed)
                print(f"Reusing {seed}: {name}", flush=True)
            else:
                protocol = expected_protocol(original, seed)
                config = trainer.TrainingConfig(**{k: protocol[k] for k in trainer.TrainingConfig.__dataclass_fields__})
                print(f"START {len(summaries)+1}/36 seed={seed} condition={name}", flush=True)
                summary = trainer.train_dataset(
                    config, results_root=output,
                    artifact_root=trainer.DEFAULT_ARTIFACT_ROOT / "multiseed" / f"seed{seed}",
                    device=torch.device("cuda"))
                verify(summary, original, seed)
            summaries.append(summary)
            save_progress()
            print(f"COMPLETE {len(summaries)}/36 seed={seed} condition={name} accuracy={summary['test']['accuracy']:.6f}", flush=True)
    from report_stl10_multiseed import main as report
    report()


if __name__ == "__main__":
    main()
