"""Run eight fixed defense/control experiments using the unchanged baseline trainer."""
from pathlib import Path
import json
import torch
import train_stl10_models as trainer
from prepare_stl10_defense import DEFENSE_ROOT, sha
from dataset_config import RESULTS_ROOT, IMAGE_ROOT


def main():
    plan_path = DEFENSE_ROOT / "selection_plan.json"
    plan = json.loads(plan_path.read_text())
    baseline = json.loads((RESULTS_ROOT / "model_training" / "comparison_summary.json").read_text())
    baselines = {s["dataset"]: s for s in baseline["summaries"]}
    for s in baselines.values():
        if s["trainer_sha256"] != sha(Path(trainer.__file__)):
            raise ValueError("Baseline trainer has changed")
        for split, key in (("val", "validation_split_sha256"), ("test", "test_split_sha256")):
            if sha(IMAGE_ROOT / f"{split}.txt") != s[key]:
                raise ValueError("Evaluation split has changed")
    trainer.MANIFEST_ROOT = DEFENSE_ROOT / "manifests"
    output = RESULTS_ROOT / "defense_training"
    artifact = trainer.DEFAULT_ARTIFACT_ROOT / "defense"
    device = torch.device("cuda")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    summaries = []
    # Attack variants first; clean variants measure the cost on uncontaminated data.
    names = sorted(plan["variants"], key=lambda n: (n.startswith("clean_subset"), n))
    for name in names:
        variant = plan["variants"][name]
        original = baselines[variant["source_dataset"]]
        if variant["source_manifest_sha256"] != original["manifest_sha256"]:
            raise ValueError("Defense source does not match original baseline")
        manifest = trainer.MANIFEST_ROOT / f"{name}.csv"
        if sha(manifest) != variant["manifest_sha256"]:
            raise ValueError("Frozen defense manifest changed")
        config_fields = trainer.TrainingConfig.__dataclass_fields__
        config = trainer.TrainingConfig(**{k:(name if k == "dataset" else original["protocol"][k]) for k in config_fields})
        previous = list((output / name).glob("*/summary.json"))
        if previous:
            if len(previous) != 1:
                raise ValueError("Ambiguous previous runs")
            summary = json.loads(previous[0].read_text())
            if (summary["status"] != "COMPLETE" or summary["manifest_sha256"] != sha(manifest)
                or summary["protocol_hash"] != original["protocol_hash"]
                or summary["trainer_sha256"] != original["trainer_sha256"]
                or not Path(summary["checkpoint"]).is_file()):
                raise ValueError("Existing run does not match frozen protocol")
            print("Reusing verified completed run:", name, flush=True)
        else:
            summary = trainer.train_dataset(config, results_root=output, artifact_root=artifact, device=device)
        assert summary["protocol_hash"] == original["protocol_hash"]
        assert summary["training_samples"] == variant["retained_samples"]
        summaries.append(summary)
        trainer.write_json(output / "defense_results.json", {
            "selection_plan_sha256": sha(plan_path), "wrapper_sha256": sha(Path(__file__)),
            "completed_runs": len(summaries), "expected_runs": len(names), "summaries": summaries})
    print("All defense and random-removal runs complete", flush=True)


if __name__ == "__main__":
    main()
