"""Development-only 128-token control versus full-coverage chunked embeddings."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics, calibrate_threshold
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/native_pairs_v1"
OUT = ROOT / "results/bipia/long_text_v1"
SNAPSHOT = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def development_rows() -> list[dict]:
    protocol = read_json(DATA / "protocol.json")
    require_hash(DATA / "samples.json", protocol["samples_sha256"])
    rows = read_json(DATA / "samples.json")
    selected = [row for row in rows if row["split"] in {"train", "validation"}]
    if len(selected) != 118:
        raise ValueError("Unexpected development partition")
    train_groups = {r["group_id"] for r in selected if r["split"] == "train"}
    validation_groups = {r["group_id"] for r in selected if r["split"] == "validation"}
    if train_groups & validation_groups:
        raise ValueError("Train/validation groups overlap")
    return selected


def joint_features(task: np.ndarray, content: np.ndarray) -> np.ndarray:
    return np.concatenate([task, content, abs(task - content), task * content,
                           np.sum(task * content, axis=1, keepdims=True)], axis=1)


def main() -> None:
    rows = development_rows()
    configs = {"legacy_prefix_128": EncodingConfig(strategy="legacy_prefix_128", window_tokens=128),
               "chunked_256_overlap32": EncodingConfig()}
    dependencies = [Path(__file__), ROOT / "s6/engineering/text_embeddings.py",
                    ROOT / "s6/engineering/artifacts.py", ROOT / "s6/engineering/metrics.py"]
    protocol = {"kind": "development-only-long-text-ablation", "seed": 2026,
                "input_sha256": file_sha256(DATA / "samples.json"),
                "partition_protocol_sha256": file_sha256(DATA / "protocol.json"),
                "code_sha256": {p.relative_to(ROOT).as_posix(): file_sha256(p) for p in dependencies},
                "arms": list(configs), "features": ["content", "joint"],
                "classifier": "LogisticRegression C=1 balanced liblinear max_iter=2000 random_state=2026",
                "threshold": "maximize validation recall at empirical FPR<=5%; tie lower FPR then higher threshold",
                "test_policy": "No test embeddings or scores. Existing test previously exposed; no new independent claim.",
                "deployment": "research only; frozen P2 and existing frontend remain unchanged"}
    with new_run(OUT, protocol):
        labels = np.array([r["label"] for r in rows])
        train = np.array([r["split"] == "train" for r in rows])
        val = ~train
        summary, predictions = {}, []
        for name, config in configs.items():
            encoder = LocalTextEncoder(SNAPSHOT, OUT / "cache", config)
            write_json(OUT / f"{name}_encoder.json", encoder.metadata)
            task, task_stats = encoder.encode([r["task"] for r in rows])
            content, content_stats = encoder.encode([r["content"] for r in rows])
            coverage = [{"id": row["id"], "split": row["split"], "task": q, "content": c}
                        for row, q, c in zip(rows, task_stats, content_stats)]
            write_json(OUT / f"{name}_coverage.json", coverage)
            if config.strategy == "chunked" and any(s["dropped_tokens"] for s in task_stats + content_stats):
                raise ValueError("Full-coverage encoder dropped tokens")
            summary[name] = {"coverage": {"documents": len(rows),
                                         "input_tokens": sum(s["input_tokens"] for s in content_stats),
                                         "dropped_tokens": sum(s["dropped_tokens"] for s in content_stats),
                                         "chunks": sum(s["chunks"] for s in content_stats)}, "features": {}}
            for feature, matrix in (("content", content), ("joint", joint_features(task, content))):
                model = LogisticRegression(C=1, class_weight="balanced", solver="liblinear",
                                           random_state=2026, max_iter=2000)
                model.fit(matrix[train], labels[train])
                scores = model.predict_proba(matrix[val])[:, 1]
                threshold, metrics = calibrate_threshold(labels[val], scores)
                summary[name]["features"][feature] = {"threshold": threshold, "validation": metrics,
                                                       "fixed_05": binary_metrics(labels[val], scores >= .5)}
                write_json(OUT / f"{name}_{feature}_classifier.json",
                           {"coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(),
                            "classes": model.classes_.tolist(), "threshold": threshold})
                for row, score in zip([r for r in rows if r["split"] == "validation"], scores):
                    predictions.append({"id": row["id"], "label": row["label"], "encoder": name,
                                        "feature": feature, "score": float(score)})
        write_json(OUT / "summary.json", summary)
        write_json(OUT / "validation_predictions.json", predictions)
        print(summary)


if __name__ == "__main__":
    main()
