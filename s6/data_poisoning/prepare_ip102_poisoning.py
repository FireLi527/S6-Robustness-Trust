"""Create reproducible IP102 clean and label-poisoning experiment manifests.

The source IP102 dataset is treated as immutable. This script references source
images and changes labels only inside generated CSV manifests.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from manifest_protocol import CANDIDATE_FIELDS, HIDDEN_GROUND_TRUTH_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IP102_ROOT = PROJECT_ROOT / "external" / "IP102"
TRAIN_ROOT = IP102_ROOT / "classification" / "train"
CLASSES_FILE = IP102_ROOT / "classes.txt"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "ip102_poisoning"
MANIFEST_ROOT = OUTPUT_ROOT / "manifests"
GROUND_TRUTH_ROOT = OUTPUT_ROOT / "hidden_ground_truth"
SUMMARY_FILE = OUTPUT_ROOT / "experiment_summary.json"

SELECTED_CLASSES = (0, 1, 3, 4, 5)
SAMPLES_PER_CLASS = 200
SEED = 2026
TARGET_SOURCE_CLASS = 0
TARGET_DESTINATION_CLASS = 1
TARGETED_RATE = 0.20

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_class_names() -> dict[int, str]:
    names: dict[int, str] = {}
    for folder_label, line in enumerate(CLASSES_FILE.read_text(encoding="utf-8").splitlines()):
        parts = line.strip().split(maxsplit=1)
        names[folder_label] = parts[1].strip() if len(parts) == 2 else parts[0]
    return names


def build_clean_manifest(class_names: dict[int, str]) -> list[dict]:
    rng = random.Random(SEED)
    records: list[dict] = []
    for label in SELECTED_CLASSES:
        class_dir = TRAIN_ROOT / str(label)
        images = sorted(class_dir.glob("*.jpg"))
        if len(images) < SAMPLES_PER_CLASS:
            raise ValueError(
                f"Class {label} has {len(images)} images; {SAMPLES_PER_CLASS} required"
            )
        for image in sorted(rng.sample(images, SAMPLES_PER_CLASS)):
            relative_path = image.relative_to(IP102_ROOT).as_posix()
            records.append(
                {
                    "sample_id": relative_path,
                    "source_relpath": relative_path,
                    "sha256": sha256_file(image),
                    "original_label": label,
                    "assigned_label": label,
                    "class_name": class_names[label],
                    "poisoned": False,
                    "poison_type": "clean",
                    "seed": SEED,
                }
            )
    return records


def random_label_flip(clean: list[dict], rate: float, seed_offset: int) -> list[dict]:
    rng = random.Random(SEED + seed_offset)
    records = [record.copy() for record in clean]
    poisoned_indexes = set(rng.sample(range(len(records)), round(len(records) * rate)))
    for index in poisoned_indexes:
        record = records[index]
        alternatives = [label for label in SELECTED_CLASSES if label != record["original_label"]]
        record["assigned_label"] = rng.choice(alternatives)
        record["poisoned"] = True
        record["poison_type"] = f"random_label_flip_{int(rate * 100):02d}"
    return records


def targeted_label_flip(clean: list[dict]) -> list[dict]:
    rng = random.Random(SEED + 20)
    records = [record.copy() for record in clean]
    candidates = [
        index
        for index, record in enumerate(records)
        if record["original_label"] == TARGET_SOURCE_CLASS
    ]
    selected = rng.sample(candidates, round(len(candidates) * TARGETED_RATE))
    for index in selected:
        records[index]["assigned_label"] = TARGET_DESTINATION_CLASS
        records[index]["poisoned"] = True
        records[index]["poison_type"] = "targeted_label_flip"
    return records


def write_candidate_manifest(name: str, records: list[dict]) -> Path:
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    output = MANIFEST_ROOT / f"{name}.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.DictWriter(destination, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: record[field] for field in CANDIDATE_FIELDS} for record in records
        )
    return output


def write_hidden_ground_truth(name: str, records: list[dict]) -> Path:
    GROUND_TRUTH_ROOT.mkdir(parents=True, exist_ok=True)
    output = GROUND_TRUTH_ROOT / f"{name}.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as destination:
        writer = csv.DictWriter(destination, fieldnames=HIDDEN_GROUND_TRUTH_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: record[field] for field in HIDDEN_GROUND_TRUTH_FIELDS}
            for record in records
        )
    return output


def describe(records: list[dict]) -> dict:
    assigned_counts = Counter(str(record["assigned_label"]) for record in records)
    poisoned = sum(bool(record["poisoned"]) for record in records)
    return {
        "samples": len(records),
        "poisoned_samples": poisoned,
        "poison_rate": round(poisoned / len(records), 4),
        "assigned_label_counts": dict(sorted(assigned_counts.items(), key=lambda item: int(item[0]))),
    }


def main() -> None:
    if not TRAIN_ROOT.is_dir() or not CLASSES_FILE.is_file():
        raise FileNotFoundError(f"Complete IP102 classification data not found at {IP102_ROOT}")

    class_names = load_class_names()
    datasets = {
        "clean_subset": build_clean_manifest(class_names),
    }
    datasets["label_flip_05"] = random_label_flip(datasets["clean_subset"], 0.05, 5)
    datasets["label_flip_10"] = random_label_flip(datasets["clean_subset"], 0.10, 10)
    datasets["targeted_0_to_1"] = targeted_label_flip(datasets["clean_subset"])

    candidate_outputs = {
        name: str(write_candidate_manifest(name, rows)) for name, rows in datasets.items()
    }
    truth_outputs = {
        name: str(write_hidden_ground_truth(name, rows)) for name, rows in datasets.items()
    }
    summary = {
        "source_dataset": str(IP102_ROOT),
        "source_is_modified": False,
        "seed": SEED,
        "selected_classes": {
            str(label): class_names[label] for label in SELECTED_CLASSES
        },
        "samples_per_class": SAMPLES_PER_CLASS,
        "datasets": {name: describe(rows) for name, rows in datasets.items()},
        "blind_protocol": {
            "version": "D1-file-split-v1",
            "candidate_fields": list(CANDIDATE_FIELDS),
            "hidden_ground_truth_fields": list(HIDDEN_GROUND_TRUTH_FIELDS),
            "physically_separate_files": True,
        },
        "manifests": candidate_outputs,
        "hidden_ground_truth": truth_outputs,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SUMMARY_FILE.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Summary: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
