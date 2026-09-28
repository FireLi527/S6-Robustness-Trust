"""Derive a deterministic, custodian-disjoint clean-email subset from the Enron corpus.

Reads the pinned parquet shard downloaded by download_enron_clean.py, keeps
each custodian's own "_sent_mail" folder (legitimate outgoing business mail --
see that script's docstring for why this heuristic and this source), filters
to a plausible email body length, deduplicates exact-duplicate bodies, and
splits by custodian (never by individual email) so no writer's style leaks
across development/unseen_test -- mirroring BIPIA's own category-disjoint
attack splits. Output records are formatted to match BIPIA's own clean-email
shape exactly (see eval_common.load_jsonl's schema), so evaluate_baseline.py
and evaluate_semantic.py can score them identically to BIPIA's clean emails.

This corpus exists to shrink the confidence interval on P1/P2's
false-positive-rate estimate. It must never be used to retune detector.py's
SIGNAL_WEIGHTS/thresholds or semantic_detector.py's REVIEW_SIMILARITY/
BLOCK_SIMILARITY -- see s6/BASELINE_ROADMAP.md's experimental-integrity rule.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import pandas as pd

from eval_common import GENERATED_DIR, PROJECT_ROOT


DEFAULT_PARQUET = PROJECT_ROOT / "external" / "enron_clean" / "0000.parquet"
SPLITS = ("development", "unseen_test")


def load_sent_mail(parquet_path: Path, min_length: int, max_length: int) -> pd.DataFrame:
    frame = pd.read_parquet(parquet_path)
    frame = frame[frame["file_name"].str.contains("_sent_mail", na=False)].copy()
    frame["custodian"] = frame["file_name"].str.split("/").str[0]
    body_length = frame["body"].str.len()
    frame = frame[(body_length >= min_length) & (body_length <= max_length)]
    frame = frame.drop_duplicates(subset=["body"])
    return frame.reset_index(drop=True)


def assign_and_sample(
    frame: pd.DataFrame,
    seed: int,
    per_split_count: int,
    per_custodian_cap: int,
) -> dict[str, pd.DataFrame]:
    """Greedily assign whole custodians to the split with fewer samples so far.

    Deterministic for a fixed (frame, seed): custodians are sorted, then
    shuffled with a seeded RNG; each custodian's own rows are shuffled with
    the same RNG stream before capping. Every custodian is assigned to at
    most one split.
    """
    rng = random.Random(seed)
    custodians = sorted(frame["custodian"].unique())
    rng.shuffle(custodians)

    targets = {split: per_split_count for split in SPLITS}
    picked: dict[str, list[int]] = {split: [] for split in SPLITS}

    for custodian in custodians:
        if all(len(picked[split]) >= targets[split] for split in SPLITS):
            break
        split = min(SPLITS, key=lambda s: (len(picked[s]) >= targets[s], len(picked[s])))
        if len(picked[split]) >= targets[split]:
            continue
        remaining = targets[split] - len(picked[split])
        indices = list(frame.index[frame["custodian"] == custodian])
        rng.shuffle(indices)
        picked[split].extend(indices[: min(per_custodian_cap, remaining, len(indices))])

    for split in SPLITS:
        if len(picked[split]) < targets[split]:
            raise ValueError(
                f"Not enough distinct-custodian clean emails for split {split!r}: "
                f"got {len(picked[split])}, need {targets[split]}. "
                "Lower --per-split-count, raise --per-custodian-cap, or download "
                "additional shards."
            )

    return {
        split: frame.loc[sorted(indices)].reset_index(drop=True)
        for split, indices in picked.items()
    }


def format_record(row: pd.Series) -> dict:
    subject = row["subject"] or ""
    from_address = row["from"] or ""
    date = row["date"]
    date_text = "" if pd.isna(date) else str(date)
    body = row["body"] or ""
    context = f"SUBJECT: {subject}|EMAIL_FROM: {from_address}|RECEIVED DATE: {date_text}|CONTENT: \n\n{body}"
    return {
        "context": context,
        "question": "",
        "source": "corbt/enron-emails",
        "message_id": row["message_id"],
        "custodian": row["custodian"],
        "file_name": row["file_name"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive an independent clean-email subset from the Enron corpus for P1/P2 FPR expansion."
    )
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--output-dir", type=Path, default=GENERATED_DIR)
    parser.add_argument("--seed", type=int, default=2023)
    parser.add_argument("--per-split-count", type=int, default=200)
    parser.add_argument("--per-custodian-cap", type=int, default=20)
    parser.add_argument("--min-length", type=int, default=60)
    parser.add_argument("--max-length", type=int, default=4000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.parquet.is_file():
        raise FileNotFoundError(
            f"Required Enron parquet shard not found: {args.parquet}\n"
            "Run download_enron_clean.py first."
        )

    frame = load_sent_mail(args.parquet, args.min_length, args.max_length)
    splits = assign_and_sample(frame, args.seed, args.per_split_count, args.per_custodian_cap)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for split, split_frame in splits.items():
        split_frame = split_frame.sort_values("message_id").reset_index(drop=True)
        records = [format_record(row) for _, row in split_frame.iterrows()]
        output_file = args.output_dir / f"enron_clean_{split}.jsonl"
        with output_file.open("w", encoding="utf-8") as destination:
            for record in records:
                destination.write(json.dumps(record, ensure_ascii=False) + "\n")
        custodians = sorted(split_frame["custodian"].unique())
        print(
            f"{split}: {len(records)} emails from {len(custodians)} custodians -> {output_file}"
        )


if __name__ == "__main__":
    main()
