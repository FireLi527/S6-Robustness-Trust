"""First-round prompt-injection accuracy experiment.

This is deliberately separate from the frozen supervised baseline.  It compares
word-only hashing with word+character hashing, task-balanced source updates, and
global versus task-specific validation thresholds.  Test data is evaluated once
after the complete variant/epoch selection is frozen.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
import sklearn
from scipy.sparse import hstack, vstack
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier

from detector import detect_prompt_injection
from supervised_data import ROOT, SEED, TASKS, catalogs, model_text, source_records, split_sources, variants
from train_supervised import metrics

OUT = ROOT / "results/bipia/supervised_v2"
DATA = ROOT / "data/bipia/supervised_v2"
GRID = np.r_[np.linspace(0, 1, 201), np.nextafter(1.0, 2.0)]


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class Features:
    def __init__(self, use_char: bool):
        self.use_char = use_char
        self.word = HashingVectorizer(
            n_features=2**18, ngram_range=(1, 2), alternate_sign=False, dtype=np.float32
        )
        self.char = HashingVectorizer(
            analyzer="char_wb", n_features=2**18, ngram_range=(3, 5),
            alternate_sign=False, dtype=np.float32
        ) if use_char else None

    def transform(self, texts):
        texts = list(texts)
        word = self.word.transform(texts)
        return hstack([word, self.char.transform(texts)], format="csr") if self.char else word


def source_batch(source, catalog, split):
    kind = "code" if source["task"] == "code" else "text"
    return list(variants(source, catalog[kind, "test" if split == "test" else "train"]))


def score_sources(model, features, sources, catalog, split):
    labels, scores, tasks = [], [], []
    for source in sources:
        batch = source_batch(source, catalog, split)
        x = features.transform(model_text(row["question"], row["context"]) for row in batch)
        scores.extend(model.predict_proba(x)[:, 1].tolist())
        labels.extend(row["label"] for row in batch)
        tasks.extend([source["task"]] * len(batch))
    return np.asarray(labels), np.asarray(scores), np.asarray(tasks)


def best_threshold(labels, scores, *, max_fpr=.05):
    best = None
    for threshold in GRID:
        result = metrics(labels, scores >= threshold)
        if result["false_positive_rate"] > max_fpr:
            continue
        key = (result["attack_detection_rate"], float(threshold))
        if best is None or key > best[0]:
            best = (key, float(threshold), result)
    if best is None:
        raise ValueError("No threshold satisfies the clean false-positive constraint")
    return best[1], best[2]


def choose_thresholds(labels, scores, tasks):
    per_task = {}
    for task in TASKS:
        take = tasks == task
        per_task[task] = best_threshold(labels[take], scores[take])
    # Global threshold must satisfy the FPR constraint in every task.
    best = None
    for threshold in GRID:
        results = {task: metrics(labels[tasks == task], scores[tasks == task] >= threshold) for task in TASKS}
        if any(value["false_positive_rate"] > .05 for value in results.values()):
            continue
        objective = float(np.mean([value["attack_detection_rate"] for value in results.values()]))
        key = (objective, float(threshold))
        if best is None or key > best[0]:
            best = (key, float(threshold), results)
    if best is None:
        raise ValueError("No global threshold satisfies every task's FPR constraint")
    return {task: value[0] for task, value in per_task.items()}, best[1], best[2]


def train_variant(name, use_char, splits, catalog):
    features = Features(use_char)
    model = SGDClassifier(loss="log_loss", alpha=1e-5, learning_rate="constant",
                          eta0=.01, average=True, random_state=SEED)
    history, best = [], None
    # Inverse source-count weights equalise total task contribution without
    # regenerating or duplicating minority-task attack variants.
    task_counts = {task: sum(row["task"] == task for row in splits["train"]) for task in TASKS}
    task_scale = {task: max(task_counts.values()) / count for task, count in task_counts.items()}
    for epoch in range(1, 4):
        rng = np.random.default_rng(SEED + epoch)
        order = rng.permutation(len(splits["train"]))
        for index in order:
            source = splits["train"][int(index)]
            batch = source_batch(source, catalog, "train")
            x = features.transform(model_text(row["question"], row["context"]) for row in batch)
            attacks = len(batch) - 1
            x = vstack([x[:attacks], x[-1][np.zeros(attacks, dtype=int)]], format="csr")
            y = np.r_[np.ones(attacks, dtype=int), np.zeros(attacks, dtype=int)]
            permutation = rng.permutation(len(y))
            weights = np.full(len(y), task_scale[source["task"]], dtype=np.float32)
            model.partial_fit(x[permutation], y[permutation], classes=np.array([0, 1]),
                              sample_weight=weights[permutation])
        labels, scores, tasks = score_sources(model, features, splits["validation"], catalog, "validation")
        task_thresholds, global_threshold, global_results = choose_thresholds(labels, scores, tasks)
        task_results = {task: metrics(labels[tasks == task], scores[tasks == task] >= task_thresholds[task])
                        for task in TASKS}
        objective = float(np.mean([value["attack_detection_rate"] for value in task_results.values()]))
        entry = {"epoch": epoch, "task_macro_recall": objective,
                 "task_thresholds": task_thresholds, "global_threshold": global_threshold,
                 "global_results": global_results, "task_results": task_results}
        history.append(entry)
        if best is None or objective > best[0]:
            best = (objective, copy.deepcopy(model), copy.deepcopy(features), entry)
    return {"name": name, "model": best[1], "features": best[2],
            "selection": best[3], "history": history}


def evaluate(bundle, sources, catalog):
    labels, scores, tasks = score_sources(bundle["model"], bundle["features"], sources, catalog, "test")
    thresholds = bundle["selection"]["task_thresholds"]
    task_predictions = np.asarray([score >= thresholds[task] for score, task in zip(scores, tasks)])
    global_predictions = scores >= bundle["selection"]["global_threshold"]
    return {
        task: {
            "task_threshold": metrics(labels[tasks == task], task_predictions[tasks == task], scores[tasks == task]),
            "global_threshold": metrics(labels[tasks == task], global_predictions[tasks == task], scores[tasks == task]),
        } for task in TASKS
    }


def main():
    start = time.time()
    if OUT.exists() or DATA.exists():
        raise RuntimeError("supervised_v2 output already exists; do not overwrite a viewed test result")
    rows, input_hashes = source_records()
    splits = split_sources(rows)
    catalog, attack_hashes, excluded = catalogs()
    input_hashes.update(attack_hashes)
    protocol = {
        "status": "FROZEN_BEFORE_TEST", "seed": SEED, "epochs": 3,
        "variants": ["word", "word_char"],
        "task_balancing": "inverse source-count loss weights; equal total source weight per task",
        "features": {"word": "word 1-2 hashing 2**18", "word_char": "plus char_wb 3-5 hashing 2**18"},
        "selection": "validation macro-task recall; each task clean FPR <=5%; compare task/global thresholds",
        "source_split_protocol": "same grouped protocol as supervised v1",
        "input_hashes": input_hashes, "excluded_attack_categories": excluded,
        "sklearn_version": sklearn.__version__,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    write(DATA / "protocol.json", protocol)
    bundles = [train_variant("word", False, splits, catalog),
               train_variant("word_char", True, splits, catalog)]
    winner = max(bundles, key=lambda item: item["selection"]["task_macro_recall"])
    selection = {"winner": winner["name"], "variants": {item["name"]: item["history"] for item in bundles}}
    write(OUT / "selection.json", selection)
    joblib.dump(winner, OUT / "model.joblib", compress=3)
    results = evaluate(winner, splits["test"], catalog)
    summary = {"status": "COMPLETE", "winner": winner["name"], "selection": winner["selection"],
               "test": results, "elapsed_seconds": time.time() - start,
               "limitations": ["Previously inspected BIPIA test; not a pristine blind test.",
                               "Generated variants are correlated and are not independent documents."]}
    write(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
