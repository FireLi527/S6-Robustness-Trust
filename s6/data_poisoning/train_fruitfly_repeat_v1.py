"""Run one preselected fruit-fly repeat in an isolated results directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

import train_stl10_models as trainer
from prepare_fruitfly import DATA, IMAGES, RESULTS, sha
from train_fruitfly_weighted_v2 import WeightedManifestDataset, weighted_train_one_epoch

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = DATA / "multiseed_v1/protocol.json"
OUTPUT = RESULTS / "multiseed_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, help="One job key from the frozen protocol")
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_BEFORE_REPEATS":
        raise ValueError("Repeat protocol is not frozen")
    if args.seed not in protocol["additional_seeds"] or args.job not in protocol["jobs"]:
        raise ValueError("Job or seed is not in the repeat protocol")
    if sha(Path(trainer.__file__)) != protocol["trainer_sha256"]:
        raise ValueError("Frozen trainer changed")
    if sha(DATA / "protocol.json") != protocol["fruitfly_protocol_sha256"]:
        raise ValueError("Fruit-fly data protocol changed")
    job = protocol["jobs"][args.job]
    manifest = ROOT / job["manifest"]
    if sha(manifest) != job["sha256"]:
        raise ValueError("Candidate manifest changed")
    for split in ("val", "test"):
        if sha(IMAGES / f"{split}.txt") != protocol[f"{split}_split_sha256"]:
            raise ValueError(f"{split} split changed")
    if args.verify_only:
        print(f"VERIFIED {args.job} seed={args.seed}")
        return
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")

    trainer.IMAGE_ROOT = IMAGES
    trainer.MANIFEST_ROOT = manifest.parent
    trainer.SELECTED_LABELS = tuple(range(5))
    trainer.LABEL_TO_INDEX = {i: i for i in range(5)}
    trainer.INDEX_TO_LABEL = {i: i for i in range(5)}
    if job["strategy"] == "weighted":
        trainer.CandidateManifestDataset = WeightedManifestDataset
        trainer.train_one_epoch = weighted_train_one_epoch

    config = trainer.TrainingConfig(
        dataset=manifest.stem, seed=args.seed, epochs=20, batch_size=32, workers=4,
        learning_rate=3e-4, weight_decay=1e-4, pretrained=True, amp=True,
        max_train_samples=None, max_eval_samples=None,
    )
    job_root = OUTPUT / manifest.stem
    prior = list(job_root.glob(f"resnet18_seed{args.seed}_*/summary.json"))
    if prior:
        if len(prior) != 1:
            raise ValueError("Ambiguous existing repeat results")
        summary = json.loads(prior[0].read_text(encoding="utf-8"))
        if (summary.get("status") != "COMPLETE" or
            summary.get("repeat_protocol_sha256") != sha(PROTOCOL) or
            summary.get("manifest_sha256") != job["sha256"] or
            not Path(summary["checkpoint"]).is_file()):
            raise ValueError("Existing result cannot be safely reused")
        print(f"REUSE {args.job} seed={args.seed}", flush=True)
        return
    if any(job_root.glob(f"resnet18_seed{args.seed}_*")):
        raise ValueError("Incomplete result directory exists; inspect before retrying")
    summary = trainer.train_dataset(
        config, results_root=OUTPUT,
        artifact_root=Path.home() / "s6-training-artifacts/fruitfly/multiseed_v1" / args.job,
        device=torch.device("cuda"),
    )
    summary.update(
        repeat_protocol_sha256=sha(PROTOCOL),
        repeat_job=args.job,
        repeat_strategy=job["strategy"],
        repeat_source=job["scenario"],
        targeted_metric_meaning="Bactrocera correcta classified as Bactrocera zonata",
    )
    (Path(summary["result_dir"]) / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"COMPLETE {args.job} seed={args.seed} accuracy={summary['test']['accuracy']:.6f}", flush=True)


if __name__ == "__main__":
    main()
