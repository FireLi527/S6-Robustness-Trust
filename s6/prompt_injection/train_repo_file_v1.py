"""Train and score a research-only repository-file classifier on frozen splits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.linear_model import LogisticRegression

from detector import detect_prompt_injection
from prepare_repo_file_splits_v1 import DATA, ROOT, load_source, sha


RESULTS = ROOT / "results/bipia/repo_file_v1"
SCRIPT = Path(__file__)
MODEL = RESULTS / "model.joblib"


def frozen_rows() -> tuple[dict, list[dict]]:
    protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
    raw, source_rows = load_source()
    assignment_path = DATA / "assignments.csv"
    if protocol["status"] != "FROZEN_BEFORE_MODEL_FITTING" or protocol["source_sha256"] != sha(raw):
        raise ValueError("Source differs from frozen split protocol")
    if protocol["assignments_sha256"] != sha(assignment_path.read_bytes()):
        raise ValueError("Frozen split assignments changed")
    with assignment_path.open(encoding="utf-8", newline="") as handle:
        assignments = list(csv.DictReader(handle))
    if len(assignments) != len(source_rows):
        raise ValueError("Assignment count differs from source")
    rows = []
    for index, (source, assignment) in enumerate(zip(source_rows, assignments)):
        if int(assignment["row_index"]) != index or int(assignment["label"]) != source["label"]:
            raise ValueError(f"Assignment mismatch at row {index}")
        if assignment["content_sha256"] != sha(source["text"].encode("utf-8")):
            raise ValueError(f"Source text changed at row {index}")
        rows.append({"index": index, "text": source["text"], "label": source["label"],
                     "split": assignment["split"], "group_id": assignment["group_id"]})
    return protocol, rows


def make_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2,
                                  max_features=50000, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=2,
                                  max_features=100000, sublinear_tf=True)),
    ])
    return Pipeline([("features", features),
                     ("model", LogisticRegression(C=1.0, class_weight="balanced",
                                                  solver="liblinear", max_iter=1000,
                                                  random_state=2026))])


def confusion(labels: np.ndarray, flags: np.ndarray) -> dict:
    positives = labels == 1
    negatives = ~positives
    tp = int(np.sum(flags & positives))
    fn = int(np.sum(~flags & positives))
    fp = int(np.sum(flags & negatives))
    tn = int(np.sum(~flags & negatives))
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "accuracy": (tp + tn) / len(labels),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None}


def select_threshold(labels: np.ndarray, scores: np.ndarray) -> tuple[float, dict]:
    candidates = sorted(set(float(x) for x in scores), reverse=True) + [0.0]
    best = None
    for threshold in candidates:
        result = confusion(labels, scores >= threshold)
        if result["fpr"] > .05:
            continue
        value = (result["recall"], -result["fpr"], threshold)
        if best is None or value > best[0]:
            best = (value, threshold, result)
    if best is None:
        raise ValueError("No threshold meets validation FPR constraint")
    return best[1], best[2]


def select() -> None:
    if (RESULTS / "selection.json").exists():
        raise FileExistsError("Model selection already frozen")
    protocol, _ = frozen_rows()
    selection = {"status": "FROZEN_BEFORE_FITTING", "script_sha256": sha(SCRIPT.read_bytes()),
                 "source_sha256": protocol["source_sha256"],
                 "assignments_sha256": protocol["assignments_sha256"],
                 "features": {"word_ngrams": [1, 2], "word_max_features": 50000,
                              "char_ngrams": [3, 5], "char_max_features": 100000,
                              "min_df": 2, "sublinear_tf": True},
                 "classifier": "LogisticRegression(C=1, class_weight=balanced, liblinear, max_iter=1000, seed=2026)",
                 "threshold_policy": "highest validation recall with benign FPR <=5%; tie: lower FPR then higher threshold",
                 "test_policy": "one evaluation after fitting and threshold freeze; external-source stress tests separate; research only"}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FROZEN model specification and test policy")


def train() -> None:
    if MODEL.exists() or (RESULTS / "validation.json").exists():
        raise FileExistsError("Model or validation result already exists")
    selection = json.loads((RESULTS / "selection.json").read_text(encoding="utf-8"))
    protocol, rows = frozen_rows()
    if selection["status"] != "FROZEN_BEFORE_FITTING" or selection["script_sha256"] != sha(SCRIPT.read_bytes()):
        raise ValueError("Training script changed since model specification freeze")
    if selection["source_sha256"] != protocol["source_sha256"] or selection["assignments_sha256"] != protocol["assignments_sha256"]:
        raise ValueError("Training data or splits changed")
    train_rows = [r for r in rows if r["split"] == "train"]
    val_rows = [r for r in rows if r["split"] == "validation"]
    pipeline = make_pipeline()
    pipeline.fit([r["text"] for r in train_rows], [r["label"] for r in train_rows])
    labels = np.asarray([r["label"] for r in val_rows], dtype=int)
    scores = pipeline.predict_proba([r["text"] for r in val_rows])[:, 1]
    threshold, val_metrics = select_threshold(labels, scores)
    joblib.dump({"pipeline": pipeline, "threshold": threshold,
                 "source_sha256": protocol["source_sha256"],
                 "assignments_sha256": protocol["assignments_sha256"]}, MODEL)
    result = {"status": "FROZEN_BEFORE_TEST", "model_sha256": sha(MODEL.read_bytes()),
              "threshold": threshold, "validation": val_metrics,
              "train_rows": len(train_rows), "validation_rows": len(val_rows),
              "limitations": protocol["limitations"]}
    (RESULTS / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def test() -> None:
    if (RESULTS / "test.json").exists():
        raise FileExistsError("Test already scored; do not overwrite")
    frozen = json.loads((RESULTS / "validation.json").read_text(encoding="utf-8"))
    if frozen["status"] != "FROZEN_BEFORE_TEST" or sha(MODEL.read_bytes()) != frozen["model_sha256"]:
        raise ValueError("Trained model changed since validation freeze")
    protocol, rows = frozen_rows()
    bundle = joblib.load(MODEL)
    if bundle["source_sha256"] != protocol["source_sha256"] or bundle["assignments_sha256"] != protocol["assignments_sha256"]:
        raise ValueError("Model has different training provenance")
    test_rows = [r for r in rows if r["split"] == "test"]
    labels = np.asarray([r["label"] for r in test_rows], dtype=int)
    scores = bundle["pipeline"].predict_proba([r["text"] for r in test_rows])[:, 1]
    predicted = scores >= bundle["threshold"]
    p1 = np.asarray([detect_prompt_injection(r["text"]).decision != "ALLOW" for r in test_rows], dtype=bool)
    summary = {"status": "COMPLETE", "source_sha256": protocol["source_sha256"],
               "model_sha256": frozen["model_sha256"], "threshold": bundle["threshold"],
               "test_rows": len(test_rows), "model": confusion(labels, predicted),
               "p1": confusion(labels, p1), "p1_or_model": confusion(labels, predicted | p1),
               "limitations": protocol["limitations"]}
    (RESULTS / "test.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (RESULTS / "test_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["row_index", "group_id", "label", "model_score", "model_flag", "p1_flag"])
        writer.writeheader()
        for row, score, flag, rule in zip(test_rows, scores, predicted, p1):
            writer.writerow({"row_index": row["index"], "group_id": row["group_id"], "label": row["label"],
                             "model_score": float(score), "model_flag": bool(flag), "p1_flag": bool(rule)})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "train", "test"))
    args = parser.parse_args()
    {"select": select, "train": train, "test": test}[args.mode]()
