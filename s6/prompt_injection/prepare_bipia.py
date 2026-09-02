"""Build a local BIPIA prompt-injection dataset without calling any LLM API."""

from __future__ import annotations

import argparse
from pathlib import Path

from bipia.data import AutoPIABuilder


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPOSITORY = PROJECT_ROOT / "external" / "BIPIA"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "bipia" / "generated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Construct BIPIA indirect prompt-injection samples."
    )
    parser.add_argument(
        "--task",
        choices=("email", "table", "code"),
        default="email",
        help="BIPIA task to construct (default: email).",
    )
    parser.add_argument(
        "--split",
        choices=("train", "test"),
        default="test",
        help="Dataset split (default: test).",
    )
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Base64-encode attack strings using BIPIA's stealth option.",
    )
    parser.add_argument("--seed", type=int, default=2023)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = args.repository.resolve()
    context_file = repository / "benchmark" / args.task / f"{args.split}.jsonl"
    attack_kind = "code" if args.task == "code" else "text"
    attack_file = repository / "benchmark" / f"{attack_kind}_attack_{args.split}.json"

    for required_file in (context_file, attack_file):
        if not required_file.is_file():
            raise FileNotFoundError(f"Required BIPIA file not found: {required_file}")

    builder = AutoPIABuilder.from_name(args.task)(seed=args.seed)
    samples = builder(
        str(context_file),
        str(attack_file),
        enable_stealth=args.stealth,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "stealth" if args.stealth else "plain"
    output_file = args.output_dir / f"{args.task}_{args.split}_{suffix}.jsonl"
    samples.to_json(output_file, orient="records", lines=True, force_ascii=False)

    print(f"Output: {output_file}")
    print(f"Rows: {len(samples)}")
    print(f"Attack variants: {samples['attack_name'].nunique()}")
    print(f"Positions: {samples['position'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
