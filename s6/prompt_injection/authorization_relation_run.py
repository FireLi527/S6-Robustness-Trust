"""Public extraction/evaluation helpers for the isolated target-relation experiment."""
from __future__ import annotations

from pathlib import Path
import numpy as np
from s6.engineering.artifacts import atomic_binary, write_json
from s6.engineering.text_embeddings import LocalTextEncoder
from s6.prompt_injection.cross_source_training import encode_records
from s6.prompt_injection.nli_authorization import FrozenNLI
from s6.prompt_injection.authorization_calibration import evaluate
from s6.prompt_injection.authorization_relation_training import scores, SEEDS


def extract(encoder: LocalTextEncoder, nli: FrozenNLI, rows: list[dict], out: Path, name: str) -> dict:
    """Strip non-text audit annotations before any encoder receives inputs."""
    inputs = [{"id": r["id"], "task": r["task"], "content": r["content"]} for r in rows]
    features, coverage = encode_records(encoder, inputs, name)
    features["task_only"] = features["joint"][:, :features["content"].shape[1]]
    probabilities, details = [], []
    for mode in ("raw_contradiction", "conflict_hypothesis"):
        _, records = nli.score(inputs, mode)
        probabilities.append(np.array([r["nli_probabilities"] for r in records]))
        details.extend(records)
    features["nli"] = np.concatenate(probabilities, axis=1)
    write_json(out / f"{name}_coverage.json", {"minilm": coverage, "nli": details})
    atomic_binary(out / f"{name}_features.npz", lambda stream: np.savez_compressed(stream, **features))
    print(f"Encoded {name}: {len(rows)} complete pairs", flush=True)
    return features


def evaluate_all(rows: list[dict], features: dict, heads: dict, out: Path, name: str) -> dict:
    """Report every seed, pair and complete quartet; never choose the best test seed."""
    summary, predictions = {}, {}
    for arm, head in heads.items():
        metrics, predicted = evaluate(rows, scores(head, features), head["threshold"])
        quartets = {}
        for row, prediction in zip(rows, predicted, strict=True):
            if row.get("quartet_id"):
                quartets.setdefault(row["quartet_id"], []).append(prediction["flag"] == row["label"])
        metrics["quartets"] = {"count": len(quartets), "all_correct": sum(all(q) for q in quartets.values())}
        summary[arm], predictions[arm] = metrics, predicted
    write_json(out / f"{name}_predictions.json", predictions)
    return summary


def seed_summary(summary: dict) -> dict:
    """Mean/sample SD across three training seeds, not independent data replicates."""
    result = {}
    for loss in ("bce", "paired"):
        arms = [summary[f"{loss}_{seed}"] for seed in SEEDS]
        result[loss] = {}
        for metric in ("accuracy", "recall", "fpr"):
            values = [a[metric] for a in arms]
            result[loss][metric] = {"mean": float(np.mean(values)), "sample_sd": float(np.std(values, ddof=1))}
        result[loss]["both_correct"] = [a["pairs"]["both_correct"] for a in arms]
        result[loss]["quartets_correct"] = [a["quartets"]["all_correct"] for a in arms]
    return result
