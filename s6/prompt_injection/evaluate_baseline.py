"""Evaluate the S6 rule baseline with fixed BIPIA development/test splits."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from detector import detect_prompt_injection, detector_metadata
from eval_common import (
    BIPIA_BENCHMARK,
    GENERATED_DIR,
    PROJECT_ROOT,
    SPLITS_DIR,
    attack_category,
    failure_rows,
    load_jsonl,
    load_selected_attacks,
    sha256_file,
    summarize_split,
)


DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "bipia"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the P1 prompt-injection baseline protocol."
    )
    parser.add_argument(
        "--encoding",
        choices=("plain", "stealth"),
        default="plain",
        help="Generated BIPIA attack encoding to evaluate (default: plain).",
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser.parse_args()


def classify(records: list[dict], ground_truth: str, split: str) -> list[dict]:
    output: list[dict] = []
    for index, record in enumerate(records):
        text = str(record["context"])
        started = time.perf_counter_ns()
        result = detect_prompt_injection(text)
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        name = str(record.get("attack_name", ""))
        output.append(
            {
                "split": split,
                "sample_id": index,
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "ground_truth": ground_truth,
                "decision": result.decision,
                "score": result.score,
                "latency_ms": round(latency_ms, 6),
                "reasons": "; ".join(result.reasons),
                "task_name": record.get("task_name", "email"),
                "attack_name": name,
                "attack_category": attack_category(name) if name else "",
                "position": record.get("position", ""),
                "question": record.get("question", ""),
            }
        )
    return output


def main() -> None:
    args = parse_args()
    split_files = {
        "development": SPLITS_DIR / "attack_development.json",
        "unseen_test": SPLITS_DIR / "attack_unseen_test.json",
    }
    attacked_files = {
        "development": GENERATED_DIR / f"email_train_{args.encoding}.jsonl",
        "unseen_test": GENERATED_DIR / f"email_test_{args.encoding}.jsonl",
    }
    clean_files = {
        "development": BIPIA_BENCHMARK / "email" / "train.jsonl",
        "unseen_test": BIPIA_BENCHMARK / "email" / "test.jsonl",
    }
    required_files = [*split_files.values(), *attacked_files.values(), *clean_files.values()]
    missing_files = [path for path in required_files if not path.is_file()]
    if missing_files:
        missing_list = "\n".join(f"- {path}" for path in missing_files)
        raise FileNotFoundError(
            "Required P1 data is missing. Run prepare_splits.py and prepare_bipia.py "
            f"for train/test first:\n{missing_list}"
        )

    decisions: list[dict] = []
    for split in ("development", "unseen_test"):
        decisions.extend(
            classify(
                load_selected_attacks(attacked_files[split], split_files[split]),
                "ATTACK",
                split,
            )
        )
        decisions.extend(classify(load_jsonl(clean_files[split]), "CLEAN", split))

    frame = pd.DataFrame(decisions)
    metadata = detector_metadata()
    summary = {
        "schema_version": 1,
        **metadata,
        "attack_encoding": args.encoding,
        "evaluation_policy": "REVIEW and BLOCK count as detected; ALLOW counts as missed",
        "historical_exposure_warning": (
            "Detector versions through 0.2.0 were developed after aggregate BIPIA test "
            "results had already been observed. Treat this as a fixed prospective split "
            "for future versions, not as a pristine blind-test claim for version 0.2.0."
        ),
        "dataset_hashes": {
            str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): sha256_file(path)
            for path in required_files
        },
        "splits": {
            split: summarize_split(frame[frame["split"] == split])
            for split in ("development", "unseen_test")
        },
    }

    args.results_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"email_p1_{args.encoding}"
    decisions_file = args.results_dir / f"{prefix}_decisions.csv"
    failures_file = args.results_dir / f"{prefix}_failures.csv"
    summary_file = args.results_dir / f"{prefix}_summary.json"
    frame.to_csv(decisions_file, index=False, encoding="utf-8-sig")
    failure_rows(frame).to_csv(failures_file, index=False, encoding="utf-8-sig")
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    compact = {
        split: {
            key: summary["splits"][split][key]
            for key in (
                "attacked_samples",
                "clean_samples",
                "attack_detection_rate",
                "false_positive_rate",
                "precision",
                "f1",
            )
        }
        for split in ("development", "unseen_test")
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    print(f"Decisions: {decisions_file}")
    print(f"Failures: {failures_file}")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
