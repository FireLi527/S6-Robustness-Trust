"""Train comparable ten-class STL-10 models from candidate-only manifests.

The training process is structurally blind to experiment ground truth. Candidate
CSV files are loaded through ``manifest_protocol.load_candidate_manifest``, which
rejects any file containing scoring-only fields. Validation and test labels come
from a held-out subset of official STL-10 train and the official test split.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms
from torchvision.models import ResNet18_Weights, resnet18

from manifest_protocol import index_unique, load_candidate_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
from dataset_config import IMAGE_ROOT
MANIFEST_ROOT = PROJECT_ROOT / "data" / "stl10_poisoning" / "manifests"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "results" / "stl10_poisoning" / "model_training"
DEFAULT_ARTIFACT_ROOT = Path.home() / "s6-training-artifacts" / "stl10"

DATASET_NAMES = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")
SELECTED_LABELS = tuple(range(10))
LABEL_TO_INDEX = {label: index for index, label in enumerate(SELECTED_LABELS)}
INDEX_TO_LABEL = {index: label for label, index in LABEL_TO_INDEX.items()}
TARGET_SOURCE_LABEL = 0
TARGET_DESTINATION_LABEL = 1

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class TrainingConfig:
    dataset: str
    seed: int
    epochs: int
    batch_size: int
    workers: int
    learning_rate: float
    weight_decay: float
    pretrained: bool
    amp: bool
    max_train_samples: int | None
    max_eval_samples: int | None


class CandidateManifestDataset(Dataset):
    """Training dataset whose source file is required to be candidate-only."""

    def __init__(
        self,
        manifest_path: Path,
        transform,
        *,
        max_samples: int | None = None,
        seed: int = 2026,
    ) -> None:
        rows = load_candidate_manifest(manifest_path)
        index_unique(rows, source=str(manifest_path))
        for row in rows:
            label = int(row["assigned_label"])
            if label not in LABEL_TO_INDEX:
                raise ValueError(f"Unsupported assigned label {label} in {manifest_path}")
            image_path = (IMAGE_ROOT / row["source_relpath"]).resolve()
            if not image_path.is_relative_to(IMAGE_ROOT.resolve()):
                raise ValueError(f"Image path escapes STL-10 root: {row['source_relpath']}")

        self.rows = _deterministic_subset(rows, max_samples, seed)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        image_path = IMAGE_ROOT / row["source_relpath"]
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        return (
            self.transform(image),
            LABEL_TO_INDEX[int(row["assigned_label"])],
            row["sample_id"],
        )


class OfficialSplitDataset(Dataset):
    """Validation held out from official train; test is the untouched official STL-10 test split."""

    def __init__(
        self,
        split: str,
        transform,
        *,
        max_samples: int | None = None,
        seed: int = 2026,
    ) -> None:
        if split not in {"val", "test"}:
            raise ValueError(f"Unsupported official split: {split}")
        rows: list[dict[str, str | int]] = []
        split_file = IMAGE_ROOT / f"{split}.txt"
        for line_number, line in enumerate(split_file.read_text(encoding="utf-8").splitlines(), 1):
            filename, label_text = line.rsplit(maxsplit=1)
            label = int(label_text)
            if label not in LABEL_TO_INDEX:
                continue
            relative_path = Path("classification") / split / str(label) / filename
            rows.append(
                {
                    "sample_id": relative_path.as_posix(),
                    "source_relpath": relative_path.as_posix(),
                    "label": label,
                    "line_number": line_number,
                }
            )
        self.rows = _deterministic_subset(rows, max_samples, seed)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        image_path = IMAGE_ROOT / str(row["source_relpath"])
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        return self.transform(image), LABEL_TO_INDEX[int(row["label"])], row["sample_id"]


def _deterministic_subset(rows: list, max_samples: int | None, seed: int) -> list:
    if max_samples is None or max_samples >= len(rows):
        return rows
    if max_samples <= 0:
        raise ValueError("Maximum sample count must be positive")
    indexes = sorted(random.Random(seed).sample(range(len(rows)), max_samples))
    return [rows[index] for index in indexes]


def training_transform():
    return transforms.Compose(
        [
            transforms.RandomResizedCrop(224, scale=(0.75, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(10),
            transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def evaluation_transform():
    return transforms.Compose(
        [
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def set_reproducible_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True, warn_only=True)


def seed_worker(worker_id: int) -> None:
    del worker_id
    worker_seed = torch.initial_seed() % (2**32)
    np.random.seed(worker_seed)
    random.seed(worker_seed)


def make_loader(
    dataset: Dataset,
    *,
    batch_size: int,
    workers: int,
    shuffle: bool,
    seed: int,
    pin_memory: bool,
) -> DataLoader:
    generator = torch.Generator()
    generator.manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=workers,
        pin_memory=pin_memory,
        persistent_workers=workers > 0,
        worker_init_fn=seed_worker,
        generator=generator,
    )


def load_class_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for folder_label, line in enumerate(
        (IMAGE_ROOT / "classes.txt").read_text(encoding="utf-8").splitlines()
    ):
        parts = line.strip().split(maxsplit=1)
        names[folder_label] = parts[1].strip() if len(parts) == 2 else parts[0]
    return names


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_model(pretrained: bool) -> nn.Module:
    weights = ResNet18_Weights.DEFAULT if pretrained else None
    model = resnet18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, len(SELECTED_LABELS))
    return model


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    scaler: torch.amp.GradScaler,
    device: torch.device,
    use_amp: bool,
) -> dict[str, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    samples = 0
    for images, labels, _sample_ids in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
            logits = model(images)
            loss = criterion(logits, labels)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        total_loss += float(loss.detach()) * labels.size(0)
        correct += int((logits.argmax(dim=1) == labels).sum())
        samples += labels.size(0)
    return {"loss": total_loss / samples, "accuracy": correct / samples}


def compute_metrics(
    labels: Sequence[int], predictions: Sequence[int], class_names: dict[int, str]
) -> dict:
    label_indexes = list(range(len(SELECTED_LABELS)))
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=label_indexes, zero_division=0
    )
    source_index = LABEL_TO_INDEX[TARGET_SOURCE_LABEL]
    destination_index = LABEL_TO_INDEX[TARGET_DESTINATION_LABEL]
    source_predictions = [
        prediction
        for truth, prediction in zip(labels, predictions)
        if truth == source_index
    ]
    targeted_rate = (
        sum(prediction == destination_index for prediction in source_predictions)
        / len(source_predictions)
        if source_predictions
        else None
    )
    per_class = {}
    for index in label_indexes:
        source_label = INDEX_TO_LABEL[index]
        per_class[str(source_label)] = {
            "class_name": class_names[source_label],
            "precision": round(float(precision[index]), 6),
            "recall": round(float(recall[index]), 6),
            "f1": round(float(f1[index]), 6),
            "support": int(support[index]),
        }
    return {
        "accuracy": round(float(accuracy_score(labels, predictions)), 6),
        "balanced_accuracy": round(float(balanced_accuracy_score(labels, predictions)), 6),
        "macro_f1": round(float(f1_score(labels, predictions, average="macro")), 6),
        "targeted_0_to_1_rate": None if targeted_rate is None else round(targeted_rate, 6),
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=label_indexes
        ).tolist(),
        "per_class": per_class,
    }


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    use_amp: bool,
    class_names: dict[int, str],
) -> tuple[dict, list[dict]]:
    model.eval()
    total_loss = 0.0
    labels_all: list[int] = []
    predictions_all: list[int] = []
    confidences_all: list[float] = []
    sample_ids_all: list[str] = []
    with torch.inference_mode():
        for images, labels, sample_ids in loader:
            images = images.to(device, non_blocking=True)
            labels_device = labels.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(images)
                loss = criterion(logits, labels_device)
            probabilities = logits.softmax(dim=1)
            confidence, predictions = probabilities.max(dim=1)
            total_loss += float(loss) * labels.size(0)
            labels_all.extend(labels.tolist())
            predictions_all.extend(predictions.cpu().tolist())
            confidences_all.extend(confidence.cpu().tolist())
            sample_ids_all.extend(sample_ids)

    metrics = compute_metrics(labels_all, predictions_all, class_names)
    metrics["loss"] = round(total_loss / len(labels_all), 6)
    metrics["samples"] = len(labels_all)
    rows = []
    for sample_id, truth_index, prediction_index, confidence in zip(
        sample_ids_all, labels_all, predictions_all, confidences_all
    ):
        truth_label = INDEX_TO_LABEL[truth_index]
        prediction_label = INDEX_TO_LABEL[prediction_index]
        rows.append(
            {
                "sample_id": sample_id,
                "true_label": truth_label,
                "true_class_name": class_names[truth_label],
                "predicted_label": prediction_label,
                "predicted_class_name": class_names[prediction_label],
                "confidence": round(confidence, 6),
                "correct": truth_index == prediction_index,
            }
        )
    return metrics, rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as destination:
        if not rows:
            return
        writer = csv.DictWriter(destination, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def environment_metadata(device: torch.device) -> dict:
    metadata = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": __import__("torchvision").__version__,
        "device": str(device),
        "cuda_runtime": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(),
    }
    if device.type == "cuda":
        properties = torch.cuda.get_device_properties(device)
        metadata.update(
            {
                "gpu": properties.name,
                "compute_capability": f"{properties.major}.{properties.minor}",
                "gpu_memory_gib": round(properties.total_memory / 1024**3, 2),
            }
        )
    return metadata


def train_dataset(
    config: TrainingConfig,
    *,
    results_root: Path,
    artifact_root: Path,
    device: torch.device,
) -> dict:
    set_reproducible_seed(config.seed)
    manifest_path = MANIFEST_ROOT / f"{config.dataset}.csv"
    class_names = load_class_names()
    train_data = CandidateManifestDataset(
        manifest_path,
        training_transform(),
        max_samples=config.max_train_samples,
        seed=config.seed,
    )
    val_data = OfficialSplitDataset(
        "val", evaluation_transform(), max_samples=config.max_eval_samples, seed=config.seed
    )
    test_data = OfficialSplitDataset(
        "test", evaluation_transform(), max_samples=config.max_eval_samples, seed=config.seed
    )
    pin_memory = device.type == "cuda"
    train_loader = make_loader(
        train_data,
        batch_size=config.batch_size,
        workers=config.workers,
        shuffle=True,
        seed=config.seed,
        pin_memory=pin_memory,
    )
    val_loader = make_loader(
        val_data,
        batch_size=config.batch_size,
        workers=config.workers,
        shuffle=False,
        seed=config.seed,
        pin_memory=pin_memory,
    )
    test_loader = make_loader(
        test_data,
        batch_size=config.batch_size,
        workers=config.workers,
        shuffle=False,
        seed=config.seed,
        pin_memory=pin_memory,
    )

    protocol = asdict(config)
    protocol.update(
        {
            "architecture": "resnet18",
            "selected_labels": list(SELECTED_LABELS),
            "optimizer": "AdamW",
            "scheduler": "CosineAnnealingLR",
            "train_transform": str(training_transform()),
            "evaluation_transform": str(evaluation_transform()),
        }
    )
    protocol_hash = canonical_hash({key: value for key, value in protocol.items() if key != "dataset"})
    run_name = f"resnet18_seed{config.seed}_{protocol_hash[:10]}"
    result_dir = results_root / config.dataset / run_name
    checkpoint_dir = artifact_root / "checkpoints" / config.dataset / run_name
    tensorboard_dir = artifact_root / "tensorboard" / config.dataset / run_name
    result_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(log_dir=str(tensorboard_dir))

    model = build_model(config.pretrained).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)
    use_amp = config.amp and device.type == "cuda"
    scaler = torch.amp.GradScaler(device.type, enabled=use_amp)
    checkpoint_path = checkpoint_dir / "best.pt"
    best_score = -1.0
    best_epoch = 0
    history: list[dict] = []
    started = time.perf_counter()

    try:
        for epoch in range(1, config.epochs + 1):
            train_metrics = train_one_epoch(
                model, train_loader, optimizer, criterion, scaler, device, use_amp
            )
            val_metrics, _ = evaluate(
                model, val_loader, criterion, device, use_amp, class_names
            )
            learning_rate = optimizer.param_groups[0]["lr"]
            row = {
                "epoch": epoch,
                "learning_rate": learning_rate,
                "train_loss": train_metrics["loss"],
                "train_accuracy": train_metrics["accuracy"],
                "val_loss": val_metrics["loss"],
                "val_accuracy": val_metrics["accuracy"],
                "val_balanced_accuracy": val_metrics["balanced_accuracy"],
                "val_macro_f1": val_metrics["macro_f1"],
            }
            history.append(row)
            for key, value in row.items():
                if key not in {"epoch"}:
                    writer.add_scalar(key, value, epoch)
            score = val_metrics["macro_f1"]
            if score > best_score:
                best_score = score
                best_epoch = epoch
                torch.save(
                    {
                        "model_state_dict": model.state_dict(),
                        "config": protocol,
                        "protocol_hash": protocol_hash,
                        "trainer_sha256": file_sha256(Path(__file__)),
                        "manifest_sha256": file_sha256(manifest_path),
                        "validation_split_sha256": file_sha256(IMAGE_ROOT / "val.txt"),
                        "test_split_sha256": file_sha256(IMAGE_ROOT / "test.txt"),
                        "pretrained_weights": (
                            ResNet18_Weights.DEFAULT.name if config.pretrained else None
                        ),
                        "best_epoch": best_epoch,
                        "validation_metrics": val_metrics,
                        "label_to_index": LABEL_TO_INDEX,
                    },
                    checkpoint_path,
                )
            scheduler.step()
            print(
                f"[{config.dataset}] epoch {epoch:02d}/{config.epochs} "
                f"train_loss={train_metrics['loss']:.4f} "
                f"val_acc={val_metrics['accuracy']:.4f} "
                f"val_f1={val_metrics['macro_f1']:.4f}"
            )
    finally:
        writer.close()

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    val_metrics, val_predictions = evaluate(
        model, val_loader, criterion, device, use_amp, class_names
    )
    test_metrics, test_predictions = evaluate(
        model, test_loader, criterion, device, use_amp, class_names
    )
    elapsed_seconds = time.perf_counter() - started

    write_csv(result_dir / "history.csv", history)
    write_csv(result_dir / "val_predictions.csv", val_predictions)
    write_csv(result_dir / "test_predictions.csv", test_predictions)
    summary = {
        "dataset": config.dataset,
        "status": "COMPLETE",
        "protocol": protocol,
        "protocol_hash": protocol_hash,
        "data_protocol": "D1-file-split-v1",
        "trainer_sha256": file_sha256(Path(__file__)),
        "manifest": str(manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "validation_split_sha256": file_sha256(IMAGE_ROOT / "val.txt"),
        "test_split_sha256": file_sha256(IMAGE_ROOT / "test.txt"),
        "pretrained_weights": ResNet18_Weights.DEFAULT.name if config.pretrained else None,
        "candidate_fields_only": True,
        "training_samples": len(train_data),
        "validation_samples": len(val_data),
        "test_samples": len(test_data),
        "assigned_label_counts": {
            str(label): sum(int(row["assigned_label"]) == label for row in train_data.rows)
            for label in SELECTED_LABELS
        },
        "best_epoch": best_epoch,
        "validation": val_metrics,
        "test": test_metrics,
        "checkpoint": str(checkpoint_path),
        "tensorboard": str(tensorboard_dir),
        "result_dir": str(result_dir),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "environment": environment_metadata(device),
    }
    write_json(result_dir / "summary.json", summary)
    print(
        f"[{config.dataset}] complete: test_acc={test_metrics['accuracy']:.4f} "
        f"test_f1={test_metrics['macro_f1']:.4f} "
        f"target_0_to_1={test_metrics['targeted_0_to_1_rate']:.4f}"
    )
    return summary


def build_comparison(summaries: list[dict]) -> dict:
    by_name = {summary["dataset"]: summary for summary in summaries}
    clean = by_name.get("clean_subset")
    comparisons = []
    if clean is not None:
        for summary in summaries:
            test = summary["test"]
            clean_test = clean["test"]
            comparisons.append(
                {
                    "dataset": summary["dataset"],
                    "accuracy": test["accuracy"],
                    "accuracy_delta_vs_clean": round(
                        test["accuracy"] - clean_test["accuracy"], 6
                    ),
                    "balanced_accuracy": test["balanced_accuracy"],
                    "balanced_accuracy_delta_vs_clean": round(
                        test["balanced_accuracy"] - clean_test["balanced_accuracy"], 6
                    ),
                    "macro_f1": test["macro_f1"],
                    "macro_f1_delta_vs_clean": round(
                        test["macro_f1"] - clean_test["macro_f1"], 6
                    ),
                    "targeted_0_to_1_rate": test["targeted_0_to_1_rate"],
                    "targeted_rate_delta_vs_clean": round(
                        test["targeted_0_to_1_rate"]
                        - clean_test["targeted_0_to_1_rate"],
                        6,
                    ),
                    "best_epoch": summary["best_epoch"],
                    "elapsed_seconds": summary["elapsed_seconds"],
                }
            )
    return {
        "research_question": (
            "How do controlled candidate-label changes affect clean held-out model behavior "
            "under an otherwise identical training protocol?"
        ),
        "summaries": summaries,
        "comparisons_vs_clean": comparisons,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASET_NAMES, default="clean_subset")
    parser.add_argument("--all", action="store_true", help="Train all four candidate datasets")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--pretrained", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-eval-samples", type=int)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.epochs <= 0 or args.batch_size <= 0 or args.workers < 0:
        raise ValueError("epochs and batch size must be positive; workers cannot be negative")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA training requested but CUDA is unavailable")
    datasets = DATASET_NAMES if args.all else (args.dataset,)
    summaries = []
    for dataset_name in datasets:
        config = TrainingConfig(
            dataset=dataset_name,
            seed=args.seed,
            epochs=args.epochs,
            batch_size=args.batch_size,
            workers=args.workers,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            pretrained=args.pretrained,
            amp=args.amp,
            max_train_samples=args.max_train_samples,
            max_eval_samples=args.max_eval_samples,
        )
        summaries.append(
            train_dataset(
                config,
                results_root=args.results_root,
                artifact_root=args.artifact_root,
                device=device,
            )
        )
    comparison = build_comparison(summaries)
    write_json(args.results_root / "comparison_summary.json", comparison)
    print(f"Comparison summary: {args.results_root / 'comparison_summary.json'}")


if __name__ == "__main__":
    main()
