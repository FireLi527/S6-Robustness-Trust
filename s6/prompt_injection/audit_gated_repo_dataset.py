"""Audit a locally authorized repository-file dataset before any model fitting.

This script never downloads data and never exports sample text. It is intended
for the gated prodnull dataset after account-level access has been granted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from supervised_data import ROOT


DEFAULT_INPUT = ROOT / "external/prompt-injection-repo-dataset/train.jsonl"
DEFAULT_OUTPUT = ROOT / "results/bipia/repo_file_dataset_v1/audit.json"


def normalized_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def audit_bytes(raw: bytes) -> dict:
    rows = []
    fields = set()
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError(f"Missing nonempty text at line {number}")
        if type(row.get("label")) is not int or row["label"] not in (0, 1):
            raise ValueError(f"Invalid binary label at line {number}")
        fields.update(row)
        rows.append(row)
    if not rows:
        raise ValueError("No data rows")
    groups = defaultdict(list)
    for row in rows:
        digest = hashlib.sha256(normalized_text(row["text"]).encode("utf-8")).hexdigest()
        groups[digest].append(row["label"])
    conflict_groups = sum(len(set(labels)) > 1 for labels in groups.values())
    exact_duplicate_rows = len(rows) - len({(row["text"], row["label"]) for row in rows})
    lengths = sorted(len(row["text"]) for row in rows)

    def quantile(q: float) -> int:
        return lengths[round((len(lengths) - 1) * q)]

    return {"status": "AUDITED_NO_TRAINING", "source_sha256": hashlib.sha256(raw).hexdigest(),
            "row_count": len(rows), "labels": {str(k): v for k, v in sorted(Counter(row["label"] for row in rows).items())},
            "fields": sorted(fields), "normalized_unique_texts": len(groups),
            "exact_duplicate_rows": exact_duplicate_rows,
            "normalized_duplicate_rows": len(rows) - len(groups),
            "conflicting_label_groups": conflict_groups,
            "text_length_chars": {"min": lengths[0], "p50": quantile(.5), "p90": quantile(.9), "max": lengths[-1]},
            "train_readiness": "NOT_READY" if conflict_groups else "REQUIRES_PROVENANCE_AND_FAMILY_REVIEW",
            "limitations": ["The released file alone does not establish repository/source or attack-family disjoint splits.",
                            "Dataset labels and benign hard negatives require spot-checking against the target trust boundary.",
                            "A separate external source must remain untouched for final evaluation."]}


def run(source: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Audit result already exists; do not overwrite")
    if not source.is_file():
        raise FileNotFoundError(source)
    result = audit_bytes(source.read_bytes())
    result["source_path"] = str(source.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output), ensure_ascii=False, indent=2))
