"""Frozen four-arm scale/task-feature study; no deployment or LLM fine tuning."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics, calibrate_threshold
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.aggregation_data import reviewed_pairs
from s6.prompt_injection.prerequisite_protocol import reviewed_candidates
from s6.prompt_injection.risk_aggregation import joint_matrix
from s6.prompt_injection.secopd_training import expand_pairs, diagnostic_overlap, paired_correct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/secopd_training_v1"


def encode_rows(encoder: LocalTextEncoder, rows: list[dict], name: str) -> tuple[dict, list[dict]]:
    """Encode complete task/body text with per-row auditable token coverage."""
    tasks, bodies, coverage = [], [], []
    for index, row in enumerate(rows):
        task, ts = encoder.encode_one(row["task"])
        body, bs = encoder.encode_one(row["content"])
        tasks.append(task)
        bodies.append(body)
        coverage.append({"id": row["id"], "task": ts, "content": bs})
        if (index + 1) % 100 == 0:
            print(f"{name}: encoded {index + 1}/{len(rows)}", flush=True)
    body_matrix = np.stack(bodies)
    return {"content": body_matrix, "joint": joint_matrix(np.stack(tasks), body_matrix)}, coverage


def score_rows(model: LogisticRegression, matrix: np.ndarray, rows: list[dict], threshold: float) -> tuple[dict, list[dict]]:
    """Persist scores/identifiers only, never redistribute source text."""
    scores = model.predict_proba(matrix)[:, 1]
    predictions = [{**{k: r[k] for k in ("id", "label", "group_id", "split")},
                    **({"pair_id": r["pair_id"]} if "pair_id" in r else {}),
                    "score": float(score), "flag": bool(score >= threshold)}
                   for r, score in zip(rows, scores, strict=True)]
    return binary_metrics(np.array([r["label"] for r in rows]), scores >= threshold), predictions


def fit_arms(features: dict, rows: list[dict]) -> tuple[dict, dict]:
    """Use only training rows for fitting and validation rows for thresholds."""
    labels = np.array([r["label"] for r in rows])
    validation = np.array([r["split"] == "validation" for r in rows])
    selections, models = {}, {}
    for size in ("small", "large"):
        train = np.array([r["split"] == "train" and (size == "large" or r["small"]) for r in rows])
        for kind in ("content", "joint"):
            arm = size + "_" + kind
            model = LogisticRegression(C=1, class_weight="balanced", solver="liblinear", max_iter=2000, random_state=2026)
            model.fit(features[kind][train], labels[train])
            threshold, metrics = calibrate_threshold(labels[validation], model.predict_proba(features[kind][validation])[:, 1])
            selections[arm] = {"threshold": threshold, "validation": metrics, "training_rows": int(train.sum()),
                               "coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(),
                               "classes": model.classes_.tolist(), "iterations": model.n_iter_.tolist()}
            models[arm] = model
            _, predictions = score_rows(model, features[kind][validation],
                                        [r for r in rows if r["split"] == "validation"], threshold)
            write_json(OUT / f"{arm}_validation.json", predictions)
            print(f"Fitted {arm}; validation={metrics}", flush=True)
    write_json(OUT / "selection.json", selections)
    return models, selections


def prepare() -> tuple[list[dict], list[dict], dict]:
    """Bind prepared data, old human decisions and protected implementation bytes."""
    folder = ROOT / "data/bipia/secopd_pairs_v1"
    source = read_json(folder / "protocol.json")
    require_hash(folder / "pairs.json", read_json(folder / "integrity.json")["pairs_sha256"])
    previous = read_json(ROOT / "results/bipia/prerequisite_training_v1/protocol.json")
    protected = {**previous["protected_sha256"], **previous["run_input_code_sha256"], **source["code_sha256"]}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    rows = expand_pairs(read_json(folder / "pairs.json"), source["small_pair_ids"])
    reference = reviewed_pairs(ROOT) + reviewed_candidates(ROOT)
    excluded = diagnostic_overlap(rows, reference)
    diagnostics = [{**r, "split": "seen_diagnostic"} for r in reference if r["id"] not in excluded]
    paths = ["s6/prompt_injection/experiment_secopd_v1.py", "s6/prompt_injection/secopd_training.py",
             "s6/prompt_injection/risk_aggregation.py", "s6/engineering/metrics.py",
             "s6/engineering/artifacts.py", "s6/engineering/text_embeddings.py",
             "data/bipia/secopd_pairs_v1/pairs.json", "data/bipia/secopd_pairs_v1/protocol.json",
             "data/bipia/repo_file_v2/human_review_completion.json",
             "data/bipia/prerequisite_review_v1/human_review_final.json"]
    protocol = {"source": source["source"], "label_basis": source["label_basis"],
                "exposure": source["exposure"], "split": source["splitting"],
                "arms": ["small_content", "small_joint", "large_content", "large_joint"],
                "primary_contrast": "large_joint minus small_joint on same-source holdout; all four reported",
                "classifier": {"C": 1, "solver": "liblinear", "class_weight": "balanced", "seed": 2026, "max_iter": 2000},
                "calibration": "maximize validation recall at empirical FPR <= .05; no test selection",
                "small_pair_ids": source["small_pair_ids"], "diagnostic_ids": [r["id"] for r in diagnostics],
                "diagnostic_overlap_excluded": excluded, "diagnostic_overlap_rule": "exact normalized task or char3-5 cosine>=.88 against all selected source rows; not semantic proof",
                "diagnostics": "Previously seen 36 reviewed rows plus 12 conditional task rows; not independent benchmark, no tuning",
                "protected_sha256": protected, "input_sha256": {p: file_sha256(ROOT / p) for p in paths}}
    return rows, diagnostics, protocol


def main() -> None:
    torch.set_num_threads(4)
    rows, diagnostics, protocol = prepare()
    snapshot = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    encoder = LocalTextEncoder(snapshot, ROOT / "external/secopd_embedding_cache_v1", EncodingConfig())
    protocol["encoder"] = encoder.metadata
    with new_run(OUT, protocol):
        development = [r for r in rows if r["split"] != "test"]
        features, coverage = encode_rows(encoder, development, "development")
        models, selection = fit_arms(features, development)
        summary = {}
        for name, subset in (("test", [r for r in rows if r["split"] == "test"]), ("seen_diagnostic", diagnostics)):
            matrices, stats = encode_rows(encoder, subset, name)
            coverage.extend(stats)
            summary[name] = {}
            for arm, model in models.items():
                kind = arm.split("_")[1]
                metrics, predictions = score_rows(model, matrices[kind], subset, selection[arm]["threshold"])
                if name == "test":
                    metrics["paired"] = paired_correct(predictions)
                else:
                    for group, prefix in (("prerequisite", "prereq-v1-"), ("earlier_review", None)):
                        chosen = [p for p in predictions if p["id"].startswith("prereq-v1-") == (prefix is not None)]
                        metrics[group] = binary_metrics(np.array([p["label"] for p in chosen]), np.array([p["flag"] for p in chosen])) if chosen else None
                summary[name][arm] = metrics
                write_json(OUT / f"{arm}_{name}.json", predictions)
        write_json(OUT / "coverage.json", coverage)
        write_json(OUT / "summary.json", summary)
        for name, digest in {**protocol["protected_sha256"], **protocol["input_sha256"]}.items():
            require_hash(ROOT / name, digest)
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
