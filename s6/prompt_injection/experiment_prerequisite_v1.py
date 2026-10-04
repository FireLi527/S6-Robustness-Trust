"""Single fixed development comparison after human review; no external execution."""
from __future__ import annotations

from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics, calibrate_threshold
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.aggregation_data import native_development, reviewed_pairs
from s6.prompt_injection.boundary_protocol import leakage_edges
from s6.prompt_injection.prerequisite_protocol import reviewed_candidates, prerequisite_folds, pair_metrics
from s6.prompt_injection.risk_aggregation import joint_matrix

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/prerequisite_training_v1"
ARMS = ("base_content", "base_joint", "added_content", "added_joint")
SNAPSHOT = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def prepare() -> tuple[list[dict], dict]:
    """Freeze labels, family isolation and model choices before fitting."""
    native, old, new = native_development(ROOT), reviewed_pairs(ROOT), reviewed_candidates(ROOT)
    rows = native + old + new
    edges = leakage_edges(rows)
    folds = prerequisite_folds(native, old, new, edges)
    prior = read_json(ROOT / "results/bipia/prerequisite_review_v1/protocol.json")
    protected = {**prior["protected_sha256"],
                 "data/bipia/prerequisite_review_v1/candidate_groups.json": prior["candidate_sha256"],
                 "s6/prompt_injection/prerequisite_review.py": prior["code_sha256"]}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    paths = ["data/bipia/prerequisite_review_v1/human_review_final.json",
             "data/bipia/prerequisite_review_v1/candidate_groups.json",
             "s6/prompt_injection/prerequisite_protocol.py", "s6/prompt_injection/experiment_prerequisite_v1.py"]
    protocol = {"folds": folds, "edges": edges, "arms": ARMS, "protected_sha256": protected,
                "run_input_code_sha256": {name: file_sha256(ROOT / name) for name in paths},
                "training": "base=native89+old reviewed36 (125); added=base+other five new families10 (135); balanced logistic regression C1/liblinear/max_iter2000/seed2026; MiniLM frozen",
                "encoding": "full coverage 256 windows overlap32 normalized weighted mean, unchanged local snapshot",
                "calibration": "native validation29 only, 23 attacks6 benign; maximize recall under empirical FPR<=5%, tie lower FPR then higher threshold; no new held-out sample calibration",
                "target": "user-reviewed task-boundary risk, not malicious intent; #8 conditional on actual execution",
                "primary": "added_joint vs base_joint; seven risk recall/five normal FPR; five opposite-label pairs both-correct and risk-score-order",
                "secondary": "content controls; fixed0.5; omit case8 from evaluation only (models still trained on it in other folds), not a label-exclusion retraining sensitivity",
                "exposure": "all synthetic development examples visible to author/reviewer; old data already used; not independent-source test",
                "limitations": "5 benign targets;6 benign calibration; five mixed-label same-body pairs fundamentally indistinguishable to content-only model; six folds dependent",
                "stop_rule": "one predeclared run; no hyperparameter search or retuning after results; no deployment, commit or push"}
    return rows, protocol


def encode(rows: list[dict]) -> tuple[dict, dict]:
    """Cache complete English inputs only; review reasons/translations excluded."""
    encoder = LocalTextEncoder(SNAPSHOT, OUT / "cache", EncodingConfig())
    write_json(OUT / "encoder.json", encoder.metadata)
    vectors, coverage = {}, []
    for row in rows:
        content, content_stats = encoder.encode_one(row["content"])
        task, task_stats = encoder.encode_one(row["task"])
        vectors[row["id"]] = {"content": content, "joint": joint_matrix(task[None, :], content[None, :])[0]}
        coverage.append({"id": row["id"], "task": task_stats, "content": content_stats})
    write_json(OUT / "coverage.json", coverage)
    return vectors, {r["id"]: r for r in rows}


def fit_models(folds: list[dict], vectors: dict, lookup: dict) -> tuple[dict, dict]:
    """Fit all folds and calibrate before any held-out predictions."""
    models, selection = {}, {}
    for fold in folds:
        key = str(fold["fold"])
        models[key], selection[key] = {}, {}
        for arm in ARMS:
            feature = arm.split("_")[1]
            train = fold["base_train"] + (fold["extra_train"] if arm.startswith("added") else [])
            cal = fold["calibration"]
            model = LogisticRegression(C=1, class_weight="balanced", solver="liblinear", random_state=2026, max_iter=2000)
            model.fit(np.stack([vectors[i][feature] for i in train]), [lookup[i]["label"] for i in train])
            scores = model.predict_proba(np.stack([vectors[i][feature] for i in cal]))[:, 1]
            threshold, metrics = calibrate_threshold(np.array([lookup[i]["label"] for i in cal]), scores)
            selection[key][arm] = {"threshold": threshold, "metrics": metrics, "train_ids": train,
                                  "calibration": [{"id": i, "label": lookup[i]["label"], "score": float(s)} for i, s in zip(cal, scores)]}
            models[key][arm] = model
            write_json(OUT / f"fold{key}_{arm}_model.json", {"coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(), "classes": model.classes_.tolist()})
    return models, selection


def metrics(rows: list[dict], field: str = "flag") -> dict:
    """Document-level counts, with risk terminology specified in the protocol."""
    return binary_metrics(np.array([r["label"] for r in rows]), np.array([r[field] for r in rows]))


def main() -> None:
    rows, protocol = prepare()
    with new_run(OUT, protocol):
        vectors, lookup = encode(rows)
        models, selection = fit_models(protocol["folds"], vectors, lookup)
        write_json(OUT / "selection.json", selection)
        predictions = {arm: [] for arm in ARMS}
        for fold in protocol["folds"]:
            key = str(fold["fold"])
            for arm in ARMS:
                ids = fold["evaluation"]
                scores = models[key][arm].predict_proba(np.stack([vectors[i][arm.split("_")[1]] for i in ids]))[:, 1]
                threshold = selection[key][arm]["threshold"]
                predictions[arm].extend({"id": i, "number": lookup[i]["number"], "group_id": fold["group"],
                                         "fold": fold["fold"], "label": lookup[i]["label"], "score": float(s),
                                         "threshold": threshold, "flag": bool(s >= threshold), "fixed05": bool(s >= .5)} for i, s in zip(ids, scores))
        write_json(OUT / "predictions.json", predictions)
        summary = {arm: {"calibrated": metrics(preds), "fixed05": metrics(preds, "fixed05"),
                          "without_case8_evaluation_only": metrics([r for r in preds if r["number"] != 8]),
                          "pairs": pair_metrics(preds)} for arm, preds in predictions.items()}
        write_json(OUT / "summary.json", summary)
        for name, digest in protocol["protected_sha256"].items():
            require_hash(ROOT / name, digest)
    print(f"COMPLETE: {OUT}", flush=True)


if __name__ == "__main__":
    main()
