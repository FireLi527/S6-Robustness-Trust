"""Evaluate P2 (semantic task-consistency) against the same fixed BIPIA splits as P1.

Produces three parallel decision systems over the *same* development/unseen_test
records used by evaluate_baseline.py, so the three can be compared honestly:

- rule:     the existing P1 rule engine alone (detector.detect_prompt_injection)
- semantic: the new P2 task-consistency signal alone (semantic_detector.assess_task_consistency)
- hybrid:   rule and semantic combined, worse decision wins (semantic_detector.combine_hybrid)

The semantic detector never sees BIPIA's attack_name/ground-truth label -- its
only inputs are each record's `question` and `context`. Per s6/BASELINE_ROADMAP.md
and CLAUDE.md's experimental-integrity rule, REVIEW_SIMILARITY/BLOCK_SIMILARITY in
semantic_detector.py were chosen by inspecting the development split only; this
script evaluates unseen_test but must not be used to retune those constants.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from detector import detect_prompt_injection
from detector import detector_metadata as rule_detector_metadata
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
from semantic_detector import (
    assess_task_consistency,
    combine_hybrid,
    extract_embeddings,
    texts_requiring_embeddings,
)
from semantic_detector import detector_metadata as semantic_detector_metadata


DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results" / "bipia"
EMBEDDING_CACHE = PROJECT_ROOT / "data" / "bipia" / "semantic_embedding_cache.npz"
MODEL_CACHE_DIR = PROJECT_ROOT / "external" / "minilm_cache"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the P2 semantic task-consistency detector and the P1+P2 hybrid."
    )
    parser.add_argument(
        "--encoding",
        choices=("plain", "stealth"),
        default="plain",
        help="Generated BIPIA attack encoding to evaluate (default: plain).",
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser.parse_args()


def classify(records: list[dict], ground_truth: str, split: str, embeddings: dict) -> list[dict]:
    output: list[dict] = []
    for index, record in enumerate(records):
        text = str(record["context"])
        question = str(record.get("question", ""))
        name = str(record.get("attack_name", ""))

        started = time.perf_counter_ns()
        rule_result = detect_prompt_injection(text)
        rule_latency_ms = (time.perf_counter_ns() - started) / 1_000_000

        started = time.perf_counter_ns()
        semantic_result = assess_task_consistency(question, text, embeddings)
        semantic_latency_ms = (time.perf_counter_ns() - started) / 1_000_000

        hybrid_decision, hybrid_reasons = combine_hybrid(
            rule_result.decision, rule_result.reasons, semantic_result
        )

        base = {
            "split": split,
            "sample_id": index,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "ground_truth": ground_truth,
            "task_name": record.get("task_name", "email"),
            "attack_name": name,
            "attack_category": attack_category(name) if name else "",
            "position": record.get("position", ""),
            "question": question,
        }
        output.append(
            {
                **base,
                "system": "rule",
                "decision": rule_result.decision,
                "score": rule_result.score,
                "latency_ms": round(rule_latency_ms, 6),
                "reasons": "; ".join(rule_result.reasons),
            }
        )
        output.append(
            {
                **base,
                "system": "semantic",
                "decision": semantic_result.decision,
                "score": semantic_result.score,
                "latency_ms": round(semantic_latency_ms, 6),
                "reasons": "; ".join(semantic_result.reasons),
            }
        )
        output.append(
            {
                **base,
                "system": "hybrid",
                "decision": hybrid_decision,
                "score": rule_result.score,
                "latency_ms": round(rule_latency_ms + semantic_latency_ms, 6),
                "reasons": "; ".join(hybrid_reasons),
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
            "Required P1/P2 data is missing. Run prepare_splits.py and prepare_bipia.py "
            f"for train/test first:\n{missing_list}"
        )

    all_records: dict[str, list[dict]] = {}
    for split in ("development", "unseen_test"):
        all_records[f"{split}_attack"] = load_selected_attacks(
            attacked_files[split], split_files[split]
        )
        all_records[f"{split}_clean"] = load_jsonl(clean_files[split])

    texts: set[str] = set()
    for records in all_records.values():
        for record in records:
            texts.update(texts_requiring_embeddings(record.get("question", ""), record["context"]))
    embeddings = extract_embeddings(list(texts), EMBEDDING_CACHE, MODEL_CACHE_DIR)

    decisions: list[dict] = []
    for split in ("development", "unseen_test"):
        decisions.extend(classify(all_records[f"{split}_attack"], "ATTACK", split, embeddings))
        decisions.extend(classify(all_records[f"{split}_clean"], "CLEAN", split, embeddings))

    frame = pd.DataFrame(decisions)
    systems = ("rule", "semantic", "hybrid")
    summary = {
        "schema_version": 1,
        "rule_detector": rule_detector_metadata(),
        "semantic_detector": semantic_detector_metadata(),
        "attack_encoding": args.encoding,
        "evaluation_policy": "REVIEW and BLOCK count as detected; ALLOW counts as missed",
        "note": (
            "'rule' reproduces the P1 baseline (detector.py) on the exact same records "
            "evaluate_baseline.py scores; 'semantic' is the new P2 task-consistency signal "
            "alone; 'hybrid' takes the more severe of the two per record. The semantic "
            "detector's REVIEW_SIMILARITY/BLOCK_SIMILARITY thresholds were calibrated on "
            "the development split only; unseen_test numbers below were not used to "
            "retune them."
        ),
        "dataset_hashes": {
            str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): sha256_file(path)
            for path in required_files
        },
        "splits": {
            split: {
                system: summarize_split(
                    frame[(frame["split"] == split) & (frame["system"] == system)]
                )
                for system in systems
            }
            for split in ("development", "unseen_test")
        },
    }

    args.results_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"email_p2_{args.encoding}"
    decisions_file = args.results_dir / f"{prefix}_decisions.csv"
    failures_file = args.results_dir / f"{prefix}_failures.csv"
    summary_file = args.results_dir / f"{prefix}_summary.json"
    frame.to_csv(decisions_file, index=False, encoding="utf-8-sig")

    all_failures = pd.concat(
        [failure_rows(frame[frame["system"] == system]) for system in systems],
        ignore_index=True,
    )
    all_failures.to_csv(failures_file, index=False, encoding="utf-8-sig")
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    compact = {
        split: {
            system: {
                key: summary["splits"][split][system][key]
                for key in (
                    "attacked_samples",
                    "clean_samples",
                    "attack_detection_rate",
                    "false_positive_rate",
                    "precision",
                    "f1",
                )
            }
            for system in systems
        }
        for split in ("development", "unseen_test")
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    print(f"Decisions: {decisions_file}")
    print(f"Failures: {failures_file}")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
