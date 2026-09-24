"""Train a risk-weighted fruit-fly condition without modifying frozen v1 code."""
import csv
import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F

import train_stl10_models as trainer
from prepare_fruitfly import DATA, IMAGES, RESULTS, sha

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = DATA / "weighted_v2"
OUTPUT = RESULTS / "weighted_v2"


class WeightedManifestDataset(trainer.CandidateManifestDataset):
    def __init__(self, manifest_path, transform, *, max_samples=None, seed=2026):
        with Path(manifest_path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = {"sample_id", "source_relpath", "sha256", "assigned_label", "risk_score", "sample_weight"}
            if set(reader.fieldnames or ()) != expected:
                raise ValueError("Unexpected weighted manifest schema")
            rows = list(reader)
        trainer.index_unique(rows, source=str(manifest_path))
        for row in rows:
            label = int(row["assigned_label"])
            if label not in trainer.LABEL_TO_INDEX:
                raise ValueError(f"Unsupported assigned label {label}")
            weight = float(row["sample_weight"])
            if not 0 < weight <= 1:
                raise ValueError("sample_weight must be in (0,1]")
            image_path = (trainer.IMAGE_ROOT / row["source_relpath"]).resolve()
            if not image_path.is_relative_to(trainer.IMAGE_ROOT.resolve()):
                raise ValueError("Image path escapes fruit-fly root")
        self.rows = trainer._deterministic_subset(rows, max_samples, seed)
        self.transform = transform

    def __getitem__(self, index):
        image, label, sample_id = super().__getitem__(index)
        return image, label, sample_id, float(self.rows[index]["sample_weight"])


def weighted_train_one_epoch(model, loader, optimizer, _criterion, scaler, device, use_amp):
    model.train(); total_loss = 0.0; correct = 0; samples = 0; weight_sum = 0.0
    for images, labels, _sample_ids, weights in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        weights = weights.to(device, dtype=torch.float32, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
            logits = model(images)
            losses = F.cross_entropy(logits, labels, reduction="none")
            loss = (losses * weights).sum() / weights.sum()
        scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()
        total_loss += float((losses.detach() * weights).sum())
        weight_sum += float(weights.sum()); correct += int((logits.argmax(1) == labels).sum()); samples += labels.size(0)
    return {"loss": total_loss / weight_sum, "accuracy": correct / samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    manifest = MANIFESTS / f"{args.dataset}.csv"
    protocol_path = MANIFESTS / "protocol.json"
    if not manifest.is_file() or not protocol_path.is_file():
        raise FileNotFoundError("Run prepare_fruitfly_weighted_v2.py first")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    expected = protocol["variants"].get(args.dataset)
    if not expected or sha(manifest) != expected["manifest_sha256"]:
        raise ValueError("Weighted manifest is not part of the frozen v2 protocol")
    trainer.IMAGE_ROOT = IMAGES
    trainer.MANIFEST_ROOT = MANIFESTS
    trainer.SELECTED_LABELS = tuple(range(5))
    trainer.LABEL_TO_INDEX = {i: i for i in range(5)}
    trainer.INDEX_TO_LABEL = {i: i for i in range(5)}
    trainer.CandidateManifestDataset = WeightedManifestDataset
    trainer.train_one_epoch = weighted_train_one_epoch
    config = trainer.TrainingConfig(dataset=args.dataset, seed=args.seed, epochs=args.epochs,
        batch_size=32, workers=4, learning_rate=3e-4, weight_decay=1e-4,
        pretrained=True, amp=True, max_train_samples=None, max_eval_samples=None)
    summary = trainer.train_dataset(config, results_root=OUTPUT,
        artifact_root=Path.home()/"s6-training-artifacts/fruitfly/weighted_v2",
        device=torch.device(args.device))
    result_path = Path(summary["result_dir"]) / "summary.json"
    summary.update(experiment="fruitfly-risk-weighted-v2", weighted_protocol_sha256=sha(protocol_path),
                   weighted_manifest_sha256=sha(manifest), sample_weight_floor=args.dataset.rsplit("_", 1)[-1])
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"COMPLETE {args.dataset} seed={args.seed} test_accuracy={summary['test']['accuracy']:.6f}")


if __name__ == "__main__":
    main()
