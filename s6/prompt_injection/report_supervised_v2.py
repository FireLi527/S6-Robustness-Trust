"""Report frozen supervised_v2 by task and encoding; never retune thresholds."""
import json

import joblib
import numpy as np

from supervised_data import ROOT, catalogs, split_sources, source_records
from train_supervised import metrics
from train_supervised_v2 import OUT, TASKS, Features, source_batch


def main():
    bundle = joblib.load(OUT / "model.joblib")
    selection = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    if bundle["name"] != selection["winner"]:
        raise ValueError("Frozen winner mismatch")
    rows, _ = source_records()
    test_sources = split_sources(rows)["test"]
    catalog, _, _ = catalogs()
    thresholds = bundle["selection"]["task_thresholds"]
    global_threshold = bundle["selection"]["global_threshold"]
    records = []
    for source in test_sources:
        batch = source_batch(source, catalog, "test")
        x = bundle["features"].transform(
            row["question"] + "\n" + row["context"] for row in batch
        )
        for row, score in zip(batch, bundle["model"].predict_proba(x)[:, 1]):
            records.append({"task": source["task"], "encoding": row["encoding"],
                            "label": row["label"], "score": float(score)})
    detailed = {}
    for task in TASKS:
        detailed[task] = {}
        for encoding in ("plain", "stealth"):
            subset = [r for r in records if r["task"] == task and r["encoding"] in (encoding, "clean")]
            labels = np.asarray([r["label"] for r in subset])
            scores = np.asarray([r["score"] for r in subset])
            detailed[task][encoding] = {
                "task_threshold": metrics(labels, scores >= thresholds[task], scores),
                "global_threshold": metrics(labels, scores >= global_threshold, scores),
            }
    output = {
        "status": "COMPLETE", "model_selection_unchanged": True,
        "winner": bundle["name"], "best_epoch": bundle["selection"]["epoch"],
        "task_thresholds": thresholds, "global_threshold": global_threshold,
        "test_by_task_and_encoding": detailed,
        "interpretation": "Post-hoc reporting of frozen decisions; no test-driven tuning.",
    }
    path = OUT / "detailed_summary.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
