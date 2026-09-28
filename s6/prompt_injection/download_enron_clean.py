"""Download a single pinned shard of the Enron email corpus for clean-corpus expansion.

Used to shrink the confidence interval on P1/P2's false-positive-rate estimate,
which otherwise rests on only BIPIA's own 50 clean emails per split (see
s6/BASELINE_ROADMAP_ZH.md). This downloads the *full* raw Enron corpus mirror
(not a spam/ham-labeled one -- the only labeled mirror readily available,
SetFit/enron_spam, lowercases text and inserts spaces around punctuation,
which would distort detector.py's regex signals). prepare_clean_corpus.py
selects legitimate clean mail from this shard via the standard Enron-corpus
research heuristic: each custodian's own "_sent_mail" folder.

Only shard 0 of 3 is downloaded -- it alone has 12,307 "_sent_mail" messages
across 34 custodians, ample for this baseline's sample size.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

from eval_common import PROJECT_ROOT


ROOT = PROJECT_ROOT / "external" / "enron_clean"
SOURCE_REPO = "corbt/enron-emails"
PARQUET_CONVERT_COMMIT = "3e55e12b80e9a5c06f9ae5ed7c6a376ead024d67"
SHARD_URL = (
    f"https://huggingface.co/datasets/{SOURCE_REPO}/resolve/"
    f"{PARQUET_CONVERT_COMMIT}/default/train/0000.parquet"
)
SHARD_SHA256 = "97165e587875e3e57715c14f63547fedbf664f748de1124122d4d2952c56a9fc"
SHARD_FILE = ROOT / "0000.parquet"


def digest_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download() -> Path:
    if SHARD_FILE.is_file() and digest_file(SHARD_FILE, "sha256") == SHARD_SHA256:
        return SHARD_FILE
    for attempt in range(3):
        try:
            with urllib.request.urlopen(SHARD_URL, timeout=120) as source, SHARD_FILE.open("wb") as dest:
                total = 0
                while block := source.read(1024 * 1024):
                    dest.write(block)
                    total += len(block)
                    if total % (20 * 1024 * 1024) == 0:
                        print("enron_clean", total // 1048576, "MiB", flush=True)
            actual = digest_file(SHARD_FILE, "sha256")
            if actual != SHARD_SHA256:
                raise ValueError(f"Checksum mismatch for {SHARD_URL}: expected {SHARD_SHA256}, got {actual}")
            return SHARD_FILE
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    path = download()
    (ROOT / "download_provenance.json").write_text(
        json.dumps(
            {
                "source_repo": SOURCE_REPO,
                "source_description": (
                    "Full raw Enron email corpus (517k messages, natural formatting). "
                    "Not the SetFit/enron_spam mirror, which is tokenized/lowercased."
                ),
                "parquet_convert_commit": PARQUET_CONVERT_COMMIT,
                "url": SHARD_URL,
                "shard": "default/train/0000.parquet (1 of 3 shards; sufficient sample size)",
                "sha256": SHARD_SHA256,
                "clean_email_heuristic": (
                    "Rows whose file_name contains '_sent_mail' are treated as a "
                    "custodian's own legitimate outgoing business mail -- the "
                    "standard heuristic used in Enron-corpus NLP research, since "
                    "this mirror carries no spam/ham label."
                ),
                "verified": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Downloaded and verified: {path}")


if __name__ == "__main__":
    main()
