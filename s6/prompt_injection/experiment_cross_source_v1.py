"""Predeclared cross-source classifier study, with separate transfer diagnostics."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.boundary_protocol import source_threshold
from s6.prompt_injection.cross_source_training import source_class_weights, encode_records, head_scores, predictions, summarize_predictions, training_indices

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/cross_source_training_v1"


def prepare_run() -> tuple[list[dict], list[dict], dict]:
    """Bind frozen splits, source bytes, legacy heads and the complete protected chain."""
    folder = ROOT / "data/bipia/cross_source_v1"
    data = read_json(folder / "protocol.json")
    protected = {**data["protected_sha256"], **data["code_sha256"]}
    protected.update({str((folder / n).relative_to(ROOT)): h for n, h in read_json(folder / "integrity.json").items()})
    source = ROOT / "external/cross_source_v1"
    require_hash(source / "manifest.json", data["source_manifest_sha256"])
    protected.update({str((source / n).relative_to(ROOT)): r["sha256"] for n, r in read_json(source / "manifest.json").items()})
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    paths = ["s6/prompt_injection/experiment_cross_source_v1.py", "s6/prompt_injection/cross_source_training.py",
             "s6/prompt_injection/boundary_protocol.py", "results/bipia/secopd_training_v1/selection.json",
             "data/bipia/cross_source_v1/protocol.json", "external/cross_source_v1/manifest.json"]
    protocol = {"protected_sha256": protected, "input_sha256": {p: file_sha256(ROOT / p) for p in paths},
                "data_protocol": "data/bipia/cross_source_v1/protocol.json", "exposure": data["exposure"],
                "scopes": ["secopd", "spml", "mixed_matched", "mixed_all"], "features": ["content", "joint"],
                "matched_training_ids": data["matched_training_ids"],
                "primary": "mixed_matched versus secopd, same mixed-source calibration; approx equal training counts; report each evaluation source separately",
                "secondary": "mixed_all scale expansion, spml-only control; frozen legacy heads isolate effects of recalibration",
                "classifier": {"C": 1, "solver": "liblinear", "max_iter": 2000, "seed": 2026,
                               "weighting": "equal source and class mass; weights sum to training row count"},
                "calibration": "pooled validation recall maximized at empirical FPR<=.05 in EACH source; tie lower pooled FPR then higher threshold",
                "notinject": "content heads only; missing trusted context is not imputed",
                "selection": "all eight heads/calibration frozen before any heldout scoring; no winner deployed, no post-test tuning",
                "source_notice": "SPML MIT card cautions contextual training may not generalize; InjecAgent MIT; NotInject MIT card; SecOPD prior noncommercial notice retained; no raw redistribution"}
    return read_json(folder / "development.json"), read_json(folder / "evaluation.json"), protocol


def train_heads(rows: list[dict], features: dict, protocol: dict) -> dict:
    """Fit eight fixed arms and calibrate each on exactly the same source partitions."""
    validation = np.array([i for i, r in enumerate(rows) if r["split"] == "validation"])
    calibration = [rows[i] for i in validation]
    labels = np.array([r["label"] for r in calibration])
    sources = np.array([r["source"] for r in calibration])
    heads = {}
    for scope in protocol["scopes"]:
        indices = training_indices(rows, scope, protocol["matched_training_ids"])
        training = [rows[i] for i in indices]
        weights = source_class_weights(training)
        for kind in protocol["features"]:
            model = LogisticRegression(C=1, solver="liblinear", max_iter=2000, random_state=2026)
            model.fit(features[kind][indices], np.array([r["label"] for r in training]), sample_weight=weights)
            head = {"feature": kind, "scope": scope, "coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(),
                    "classes": model.classes_.tolist(), "iterations": model.n_iter_.tolist(),
                    "training_counts": {source: {str(label): sum(r["source"] == source and r["label"] == label for r in training)
                                               for label in (0, 1)} for source in sorted({r["source"] for r in training})}}
            scores = head_scores(head, features[kind][validation])
            threshold, metrics = source_threshold(labels, scores, sources)
            head.update(threshold=threshold, calibration=metrics)
            arm = f"{scope}_{kind}"
            heads[arm] = head
            write_json(OUT / f"{arm}_validation.json", predictions(head, features[kind][validation], calibration))
            print(f"Fitted {arm}: rows={len(training)}, threshold={threshold:.6f}, validation={metrics['pooled']}", flush=True)
    legacy = read_json(ROOT / "results/bipia/secopd_training_v1/selection.json")
    for kind in protocol["features"]:
        heads[f"legacy_{kind}"] = {**legacy[f"large_{kind}"], "feature": kind, "scope": "legacy",
                                    "note": "previous unchanged head AND previous SecOPD-only calibration"}
    write_json(OUT / "selection.json", heads)
    return heads


def evaluate(heads: dict, rows: list[dict], encoder: LocalTextEncoder) -> tuple[dict, list[dict]]:
    """Evaluate sources separately after saved selection; no missing-context scores."""
    summary, coverage = {}, []
    for source in sorted({r["source"] for r in rows}):
        subset = [r for r in rows if r["source"] == source]
        features, stats = encode_records(encoder, subset, source)
        coverage.extend(stats)
        summary[source] = {}
        for arm, head in heads.items():
            if head["feature"] not in features:
                summary[source][arm] = {"skipped": "No trusted context field; no invented task"}
                continue
            scored = predictions(head, features[head["feature"]], subset)
            summary[source][arm] = summarize_predictions(scored)
            write_json(OUT / f"{arm}_{source}.json", scored)
        print(f"Evaluated {source}: {len(subset)} rows", flush=True)
    return summary, coverage


def main() -> None:
    torch.set_num_threads(4)
    all_rows, external, protocol = prepare_run()
    rows = [r for r in all_rows if r["split"] != "test"]
    holdout = [r for r in all_rows if r["split"] == "test"]
    snapshot = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    encoder = LocalTextEncoder(snapshot, ROOT / "external/secopd_embedding_cache_v1", EncodingConfig())
    protocol["encoder"] = encoder.metadata
    with new_run(OUT, protocol):
        features, coverage = encode_records(encoder, rows, "development")
        heads = train_heads(rows, features, protocol)
        summary, evaluation_coverage = evaluate(heads, holdout + external, encoder)
        write_json(OUT / "summary.json", summary)
        write_json(OUT / "coverage.json", coverage + evaluation_coverage)
        for name, digest in {**protocol["protected_sha256"], **protocol["input_sha256"]}.items():
            require_hash(ROOT / name, digest)
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
