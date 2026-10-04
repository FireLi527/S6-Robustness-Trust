"""External-source stress checks for the frozen research-only repo-file model."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from detector import detect_prompt_injection
from train_repo_file_v1 import MODEL, RESULTS, confusion, frozen_rows, sha


ROOT = Path(__file__).resolve().parents[2]
REPOGUARD = ROOT / "data/bipia/code_external_v1/samples.jsonl"
AIB = ROOT / "data/bipia/code_context_v2/samples.jsonl"
ASHWIN = ROOT / "external/prompt-injection-benchmark/dataset/v1.0.0/full.jsonl"
MAINTAINER = ROOT / "data/bipia/maintainer_negatives_v1/samples.jsonl"
INDIRECT = {"tool_output", "retrieved_document", "web_content", "file_upload"}


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def external_cases() -> list[dict]:
    cases = []
    for row in read_rows(REPOGUARD):
        if row["kind"] not in {"benchmark_attack", "benchmark_clean"}:
            continue
        cases.append({"source": "RepoGuardBench", "id": f"{row['source_id']}/{row.get('goal', 'clean')}",
                      "label": int(row["kind"] == "benchmark_attack"), "text": row["content"]})
    for row in read_rows(AIB):
        if row["kind"] == "external_file_content":
            cases.append({"source": "AgentInjectionBench", "id": row["source_id"],
                          "label": int(row["label"] == "unsafe"), "text": row["content"]})
    for row in read_rows(ASHWIN):
        if row["channel"] in INDIRECT:
            cases.append({"source": "prompt-injection-benchmark", "id": row["id"],
                          "label": int(row["label"] == "injection"), "text": row["text"]})
    for row in read_rows(MAINTAINER):
        cases.append({"source": "maintainer_candidates", "id": row["source_id"],
                      "label": None, "text": row["content"]})
    counts = {name: sum(row["source"] == name for row in cases)
              for name in ("RepoGuardBench", "AgentInjectionBench", "prompt-injection-benchmark", "maintainer_candidates")}
    if counts != {"RepoGuardBench": 564, "AgentInjectionBench": 10,
                  "prompt-injection-benchmark": 17, "maintainer_candidates": 30}:
        raise ValueError(f"External composition changed: {counts}")
    return cases


def normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def evaluate() -> None:
    output = RESULTS / "external.json"
    if output.exists():
        raise FileExistsError("External stress test already scored")
    frozen = json.loads((RESULTS / "validation.json").read_text(encoding="utf-8"))
    if frozen["status"] != "FROZEN_BEFORE_TEST" or sha(MODEL.read_bytes()) != frozen["model_sha256"]:
        raise ValueError("Model changed after validation freeze")
    bundle = joblib.load(MODEL)
    _, source_rows = frozen_rows()
    training_texts = {hashlib.sha256(normalized(row["text"]).encode()).hexdigest()
                      for row in source_rows if row["split"] == "train"}
    cases = external_cases()
    scores = bundle["pipeline"].predict_proba([row["text"] for row in cases])[:, 1]
    flags = scores >= bundle["threshold"]
    rules = np.asarray([detect_prompt_injection(row["text"]).decision != "ALLOW" for row in cases], dtype=bool)
    predictions = []
    for row, score, flag, rule in zip(cases, scores, flags, rules):
        text_hash = hashlib.sha256(normalized(row["text"]).encode()).hexdigest()
        predictions.append({"source": row["source"], "id": row["id"], "label": row["label"],
                            "normalized_text_sha256": text_hash, "exact_training_overlap": text_hash in training_texts,
                            "model_score": float(score), "model_flag": bool(flag), "p1_flag": bool(rule)})
    groups = {}
    for name in ("RepoGuardBench", "AgentInjectionBench", "prompt-injection-benchmark"):
        subset = [row for row in predictions if row["source"] == name]
        labels = np.asarray([row["label"] for row in subset], dtype=int)
        model_flags = np.asarray([row["model_flag"] for row in subset], dtype=bool)
        rule_flags = np.asarray([row["p1_flag"] for row in subset], dtype=bool)
        groups[name] = {"count": len(subset), "exact_training_overlap": sum(row["exact_training_overlap"] for row in subset),
                        "model": confusion(labels, model_flags), "p1": confusion(labels, rule_flags)}
    maintainer = [row for row in predictions if row["source"] == "maintainer_candidates"]
    summary = {"status": "COMPLETE_RESEARCH_ONLY", "model_sha256": frozen["model_sha256"],
               "threshold": bundle["threshold"], "sources": groups,
               "maintainer_unreviewed": {"count": len(maintainer),
                                         "model_flagged": sum(row["model_flag"] for row in maintainer),
                                         "p1_flagged": sum(row["p1_flag"] for row in maintainer),
                                         "exact_training_overlap": sum(row["exact_training_overlap"] for row in maintainer),
                                         "warning": "Flagged count, not FPR: no independent benign labels."},
               "limitations": ["RepoGuardBench has five repeated attack templates across 94 tasks; row counts are correlated.",
                               "AgentInjectionBench has only eight unsafe and two safe file-content cases.",
                               "prompt-injection-benchmark is an adjacent indirect-input domain, not a repository-only corpus.",
                               "Exact normalized-string overlap check does not rule out paraphrase or source-family overlap."]}
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (RESULTS / "external_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    evaluate()
