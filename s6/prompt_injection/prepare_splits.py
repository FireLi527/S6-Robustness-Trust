"""Create deterministic, category-disjoint BIPIA development and test manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPOSITORY = PROJECT_ROOT / "external" / "BIPIA"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "bipia" / "splits"


def _load_catalog(path: Path) -> dict[str, list[str]]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError(f"Attack catalog must be a non-empty object: {path}")
    for category, attacks in catalog.items():
        if not isinstance(category, str) or not isinstance(attacks, list):
            raise ValueError(f"Invalid attack catalog entry in {path}: {category!r}")
        if not attacks or not all(isinstance(attack, str) for attack in attacks):
            raise ValueError(f"Attack category must contain strings: {category!r}")
    return catalog


def _catalog_records(
    catalog: dict[str, list[str]], included_categories: list[str]
) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for category in included_categories:
        for variant, attack_text in enumerate(catalog[category]):
            records.append(
                {
                    "attack_name": f"{category}-{variant}",
                    "category": category,
                    "variant": variant,
                    "attack_text_sha256": hashlib.sha256(
                        attack_text.encode("utf-8")
                    ).hexdigest(),
                }
            )
    return records


def build_split_manifests(
    development_catalog: dict[str, list[str]],
    test_catalog: dict[str, list[str]],
) -> tuple[dict, dict]:
    """Build manifests while excluding every category shared with final test."""
    overlap = set(development_catalog).intersection(test_catalog)
    development_categories = [
        category for category in development_catalog if category not in overlap
    ]
    unseen_categories = list(test_catalog)

    development = {
        "schema_version": 1,
        "split": "development",
        "source_bipia_split": "train",
        "selection_policy": "all BIPIA train categories not present in BIPIA test",
        "excluded_overlapping_categories": sorted(overlap),
        "categories": development_categories,
        "attacks": _catalog_records(development_catalog, development_categories),
    }
    unseen_test = {
        "schema_version": 1,
        "split": "unseen_test",
        "source_bipia_split": "test",
        "selection_policy": "all BIPIA test categories",
        "categories": unseen_categories,
        "attacks": _catalog_records(test_catalog, unseen_categories),
    }

    if set(development["categories"]).intersection(unseen_test["categories"]):
        raise AssertionError("Development and unseen-test categories must be disjoint")
    return development, unseen_test


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create fixed BIPIA attack split manifests for S6 P1."
    )
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark = args.repository.resolve() / "benchmark"
    train_file = benchmark / "text_attack_train.json"
    test_file = benchmark / "text_attack_test.json"
    for required_file in (train_file, test_file):
        if not required_file.is_file():
            raise FileNotFoundError(f"Required BIPIA file not found: {required_file}")

    development, unseen_test = build_split_manifests(
        _load_catalog(train_file), _load_catalog(test_file)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        args.output_dir / "attack_development.json": development,
        args.output_dir / "attack_unseen_test.json": unseen_test,
    }
    for output_file, manifest in outputs.items():
        output_file.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"{manifest['split']}: {len(manifest['categories'])} categories, "
            f"{len(manifest['attacks'])} attack variants -> {output_file}"
        )


if __name__ == "__main__":
    main()
