"""Verify official STL-10 and prepare deterministic candidate-only poisoning data.

Download the official archive to external/STL10/stl10_binary.tar.gz first.
Generated PNGs and manifests live under data/, never inside the upstream archive.
"""
from __future__ import annotations

import hashlib
import json
import random
import tarfile
from pathlib import Path

import numpy as np
from PIL import Image

import prepare_ip102_poisoning as manifest_builder
from dataset_config import DATA_ROOT, IMAGE_ROOT, PROJECT_ROOT, SELECTED_LABELS

ARCHIVE = PROJECT_ROOT / "external" / "STL10" / "stl10_binary.tar.gz"
ARCHIVE_MD5 = "91f7769df0f17e558f3565bffb0c7dfb"
MEMBER_MD5 = {
    "train_X.bin": "918c2871b30a85fa023e0c44e0bee87f",
    "train_y.bin": "5a34089d4802c674881badbb80307741",
    "test_X.bin": "7f263ba9f9e0b06b93213547f721ac82",
    "test_y.bin": "36f9794fa4beb8a2c72628de14fa638e",
}
SEED = 2026


def digest_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_verified() -> Path:
    binary = ARCHIVE.parent / "stl10_binary"
    if all((binary / name).is_file() and digest_file(binary / name, "md5") == checksum
           for name, checksum in MEMBER_MD5.items()) and (binary / "class_names.txt").is_file():
        return binary
    if not ARCHIVE.is_file() or digest_file(ARCHIVE, "md5") != ARCHIVE_MD5:
        raise ValueError("Missing/incomplete STL-10 archive or official MD5 mismatch")
    binary.mkdir(parents=True, exist_ok=True)
    # Explicit allowlist; never extract archive-controlled paths or links.
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for name in (*MEMBER_MD5, "class_names.txt", "fold_indices.txt"):
            member = archive.getmember(f"stl10_binary/{name}")
            if not member.isfile():
                raise ValueError(f"Unexpected archive member: {name}")
            with archive.extractfile(member) as source, (binary / name).open("wb") as dest:
                import shutil
                shutil.copyfileobj(source, dest)
    for name, checksum in MEMBER_MD5.items():
        if digest_file(binary / name, "md5") != checksum:
            raise ValueError(f"Official checksum mismatch: {name}")
    return binary


def split_train(labels: np.ndarray) -> tuple[set[int], set[int]]:
    rng = random.Random(SEED)
    train, val = set(), set()
    for label in SELECTED_LABELS:
        indices = np.flatnonzero(labels == label).tolist()
        if len(indices) != 500:
            raise ValueError(f"Expected 500 official training images for class {label}")
        rng.shuffle(indices)
        val.update(indices[:100])
        train.update(indices[100:])
    return train, val


def main() -> None:
    binary = extract_verified()
    names = (binary / "class_names.txt").read_text().splitlines()
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (IMAGE_ROOT / "classes.txt").write_text(
        "\n".join(f"{i} {name}" for i, name in enumerate(names)) + "\n", encoding="utf-8")
    records, split_lines = [], {"train": [], "val": [], "test": []}
    for official_split, expected in (("train", 5000), ("test", 8000)):
        labels = np.fromfile(binary / f"{official_split}_y.bin", dtype=np.uint8).astype(int) - 1
        # Official channel-major, column-major pixels -> HWC, no image recompression.
        images = np.memmap(binary / f"{official_split}_X.bin", mode="r", dtype=np.uint8,
                           shape=(expected, 3, 96, 96)).transpose(0, 3, 2, 1)
        if len(labels) != expected or set(labels) != set(SELECTED_LABELS):
            raise ValueError("Unexpected STL-10 labels")
        train_indices, _ = split_train(labels) if official_split == "train" else (set(), set())
        for index, label in enumerate(labels):
            split = "test" if official_split == "test" else ("train" if index in train_indices else "val")
            filename = f"{official_split}_{index:05d}.png"
            rel = Path("classification") / split / str(label) / filename
            path = IMAGE_ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(images[index]).save(path)
            split_lines[split].append(f"{filename} {label}")
            if split == "train":
                records.append(dict(sample_id=rel.as_posix(), source_relpath=rel.as_posix(),
                                    sha256=digest_file(path, "sha256"), original_label=int(label),
                                    assigned_label=int(label), poisoned=False, poison_type="clean",
                                    class_name=names[label], seed=SEED))
        print(f"Exported official {official_split}: {expected} PNGs", flush=True)
    for split, lines in split_lines.items():
        (IMAGE_ROOT / f"{split}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_builder.SELECTED_CLASSES = SELECTED_LABELS
    manifest_builder.MANIFEST_ROOT = DATA_ROOT / "manifests"
    manifest_builder.GROUND_TRUTH_ROOT = DATA_ROOT / "hidden_ground_truth"
    datasets = {
        "clean_subset": records,
        "label_flip_05": manifest_builder.random_label_flip(records, 0.05, 5),
        "label_flip_10": manifest_builder.random_label_flip(records, 0.10, 10),
        "targeted_0_to_1": manifest_builder.targeted_label_flip(records),
    }
    for name, rows in datasets.items():
        manifest_builder.write_candidate_manifest(name, rows)
        manifest_builder.write_hidden_ground_truth(name, rows)
    summary = {
        "dataset": "STL-10", "seed": SEED, "official_binary_md5": MEMBER_MD5,
        "source_url": "https://ai.stanford.edu/~acoates/stl10/stl10_binary.tar.gz",
        "classes": dict(enumerate(names)), "split_sizes": {k: len(v) for k, v in split_lines.items()},
        "protocol": "Custom S6 label-poisoning protocol, not the official STL-10 fold benchmark. "
                    "400/class candidate training, 100/class validation from official train; "
                    "official test untouched. Unlabeled images are not used or extracted.",
        "targeted_attack": "20% of airplane (0) labels flipped to bird (1); 2% of all candidates",
        "datasets": {name: manifest_builder.describe(rows) for name, rows in datasets.items()},
    }
    (DATA_ROOT / "experiment_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
