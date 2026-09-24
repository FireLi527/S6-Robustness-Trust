"""Download a pinned labeled STL-10 mirror and verify official binary checksums.

The unlabeled archive is unnecessary for this supervised poisoning protocol.
Requires pyarrow only for this download/conversion step.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from io import BytesIO
import hashlib
import json
import time
import urllib.request
import numpy as np
from PIL import Image
from dataset_config import PROJECT_ROOT
from prepare_stl10_poisoning import MEMBER_MD5, digest_file

ROOT = PROJECT_ROOT / "external" / "STL10"
REVISION = "49ae7f94508f7feae62baf836db284306eab0b0f"
CHECKSUMS = {
    "train": "b450f19e41454731be0bcddc7093fcf9793fe9b64ea795e6ef18ca77f34c353d",
    "test": "298b23e983c755dfba2c69dec181340221deb1a5ad6651990c7c5c559fb892be",
}
CLASS_NAMES = ("airplane", "bird", "car", "cat", "deer", "dog", "horse", "monkey", "ship", "truck")


def download(split):
    path = ROOT / f"{split}.parquet"
    if path.is_file() and digest_file(path, "sha256") == CHECKSUMS[split]:
        return path
    url = f"https://huggingface.co/datasets/tanganke/stl10/resolve/{REVISION}/data/{split}-00000-of-00001.parquet"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=90) as source, path.open("wb") as dest:
                total = 0
                while block := source.read(1024 * 1024):
                    dest.write(block)
                    total += len(block)
                    if total % (20 * 1024 * 1024) == 0:
                        print(split, total // 1048576, "MiB", flush=True)
            if digest_file(path, "sha256") != CHECKSUMS[split]:
                raise ValueError(f"Mirror checksum mismatch: {split}")
            return path
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2)


def restore(split, path):
    import pyarrow.parquet as pq
    rows = pq.read_table(path).to_pylist()
    if len(rows) != {"train": 5000, "test": 8000}[split]:
        raise ValueError("Unexpected mirror split size")
    indices = [int(Path(row["image"]["path"]).stem) for row in rows]
    if set(indices) != set(range(len(rows))) or len(set(indices)) != len(rows):
        raise ValueError("Mirror original sample indices are not unique and complete")
    rows.sort(key=lambda row: int(Path(row["image"]["path"]).stem))
    binary = ROOT / "stl10_binary"
    binary.mkdir(parents=True, exist_ok=True)
    with (binary / f"{split}_X.bin").open("wb") as images:
        labels = []
        for row in rows:
            with Image.open(BytesIO(row["image"]["bytes"])) as image:
                pixels = np.asarray(image.convert("RGB"))
            if pixels.shape != (96, 96, 3):
                raise ValueError("Unexpected mirror image dimensions")
            images.write(pixels.transpose(2, 1, 0).tobytes())
            labels.append(int(row["label"]) + 1)
    np.asarray(labels, dtype=np.uint8).tofile(binary / f"{split}_y.bin")
    for suffix in ("X", "y"):
        name = f"{split}_{suffix}.bin"
        actual = digest_file(binary / name, "md5")
        if actual != MEMBER_MD5[name]:
            raise ValueError(f"Official binary checksum mismatch: {name} ({actual})")
    print(f"{split}: official image and label MD5 checks passed", flush=True)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(download, ("train", "test")))
    for split, path in zip(("train", "test"), paths):
        restore(split, path)
    (ROOT / "stl10_binary" / "class_names.txt").write_text("\n".join(CLASS_NAMES) + "\n")
    (ROOT / "download_provenance.json").write_text(json.dumps({
        "official_homepage": "https://cs.stanford.edu/~acoates/stl10/",
        "mirror": "tanganke/stl10", "revision": REVISION,
        "parquet_sha256": CHECKSUMS, "official_binary_md5": MEMBER_MD5,
        "verified": True, "unlabeled_downloaded": False,
    }, indent=2))


if __name__ == "__main__":
    main()
