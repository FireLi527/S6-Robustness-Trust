"""Independently reconstruct saved predictions and audit experimental boundaries."""
from __future__ import annotations

from pathlib import Path
import numpy as np
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.boundary_protocol import source_threshold
from s6.prompt_injection.cross_source_training import head_scores, summarize_predictions
from s6.prompt_injection.risk_aggregation import joint_matrix


def validate_partitions(rows: list[dict], matched: dict) -> dict:
    """Reject any group or identifier shared between training, calibration and test."""
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate development id")
    owners = {}
    for row in rows:
        key = row["source"], row["group_id"]
        if owners.setdefault(key, row["split"]) != row["split"]:
            raise ValueError("Cross-partition group leakage")
    train = {r["id"]: r for r in rows if r["split"] == "train"}
    for source, identifiers in matched.items():
        if len(set(identifiers)) != len(identifiers) or any(i not in train or train[i]["source"] != source for i in identifiers):
            raise ValueError("Invalid matched training ids")
        groups = {train[i]["group_id"] for i in identifiers}
        if any(r["id"] not in identifiers for r in train.values() if r["source"] == source and r["group_id"] in groups):
            raise ValueError("Matched control split a group")
    return {source: {split: {"rows": sum(r["source"] == source and r["split"] == split for r in rows),
                              "groups": len({r["group_id"] for r in rows if r["source"] == source and r["split"] == split})}
                     for split in ("train", "validation", "test")}
            for source in sorted({r["source"] for r in rows})}


def cached_features(root: Path, coverage: dict, identifiers: list[str], kind: str) -> np.ndarray:
    """Load existing frozen vectors only; no encoder or model inference."""
    vectors = []
    for identifier in identifiers:
        record = coverage[identifier]
        fields = ["content"] if kind == "content" else ["task", "content"]
        items = []
        for field in fields:
            stat = record[field]
            if stat is None:
                raise ValueError("Joint model cannot score a missing context")
            path = root / "external/secopd_embedding_cache_v1" / stat["encoder"] / (stat["text_sha256"] + ".npz")
            with np.load(path, allow_pickle=False) as saved:
                items.append(saved["vector"].copy())
        vectors.append(items[0] if kind == "content" else joint_matrix(items[0][None, :], items[1][None, :])[0])
    return np.stack(vectors)


def verify_predictions(root: Path, folder: Path, heads: dict, coverage: dict, reference: dict) -> dict:
    """Recompute probabilities, flags, validation thresholds and every source metric."""
    summary = read_json(folder / "summary.json")
    max_error, checked = 0.0, 0
    for arm, head in heads.items():
        names = [source for source in summary if "skipped" not in summary[source][arm]]
        if head["scope"] != "legacy":
            names.append("validation")
        for name in names:
            rows = read_json(folder / f"{arm}_{name}.json")
            for row in rows:
                original = reference[row["id"]]
                if any(row[k] != original[k] for k in ("label", "source", "split", "group_id")):
                    raise ValueError("Prediction metadata differs from frozen input")
            matrix = cached_features(root, coverage, [r["id"] for r in rows], head["feature"])
            scores = head_scores(head, matrix)
            error = float(abs(scores - np.array([r["score"] for r in rows])).max())
            max_error = max(max_error, error)
            if error > 1e-12 or any(r["flag"] != bool(score >= head["threshold"]) for r, score in zip(rows, scores, strict=True)):
                raise ValueError("Prediction reconstruction mismatch")
            if name == "validation":
                threshold, metrics = source_threshold(np.array([r["label"] for r in rows]), scores, np.array([r["source"] for r in rows]))
                if threshold != head["threshold"] or metrics != head["calibration"]:
                    raise ValueError("Calibration reconstruction mismatch")
            elif summarize_predictions(rows) != summary[name][arm]:
                raise ValueError("Summary reconstruction mismatch")
            checked += len(rows)
    return {"prediction_rows_reconstructed": checked, "max_probability_error": max_error}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    folder = root / "results/bipia/cross_source_training_v1"
    if read_json(folder / "status.json")["state"] != "COMPLETE":
        raise ValueError("Experiment must complete before verification")
    protocol = read_json(folder / "protocol.json")
    protected = {**protocol["protected_sha256"], **protocol["input_sha256"]}
    for name, digest in protected.items():
        require_hash(root / name, digest)
    data = root / "data/bipia/cross_source_v1"
    development, external = read_json(data / "development.json"), read_json(data / "evaluation.json")
    partition = validate_partitions(development, protocol["matched_training_ids"])
    heads, coverage_rows = read_json(folder / "selection.json"), read_json(folder / "coverage.json")
    coverage = {r["id"]: r for r in coverage_rows}
    reference = {r["id"]: r for r in development + external}
    if len(coverage) != len(coverage_rows) or set(coverage) != set(reference):
        raise ValueError("Missing or repeated coverage rows")
    stats = [row[k] for row in coverage_rows for k in ("task", "content") if row[k] is not None]
    if any(s["dropped_tokens"] or s["covered_tokens"] != s["input_tokens"] for s in stats):
        raise ValueError("Incomplete token coverage")
    old = read_json(root / "results/bipia/secopd_training_v1/selection.json")
    for kind in ("content", "joint"):
        if any(heads[f"legacy_{kind}"][k] != old[f"large_{kind}"][k] for k in ("coef", "intercept", "threshold", "classes")):
            raise ValueError("Legacy model was altered")
    report = {"protected_files": len(protected), "partition": partition, "coverage_rows": len(coverage),
              "max_tokens": max(s["input_tokens"] for s in stats), "multi_window_inputs": sum(s["chunks"] > 1 for s in stats),
              "dropped_tokens": 0, **verify_predictions(root, folder, heads, coverage, reference)}
    with new_run(folder / "verification", {"code_sha256": file_sha256(Path(__file__)), "kind": "post-run verification only"}):
        write_json(folder / "verification/result.json", report)
    print(report, flush=True)


if __name__ == "__main__":
    main()
