"""Evaluate a preselected comment-aware signal, development then confirmation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from code_context_signal import assess_comment_redirection
from detector import detect_prompt_injection
from evaluate_code_independent_v2 import DATA as PRIOR_DATA, RESULTS as PRIOR_RESULTS, ROOT, digest, rates
from supervised_data import model_text
from supervised_detector import ARTIFACT, SELECTION, _load

DATA = ROOT / "data/bipia/code_context_v1"
RESULTS = ROOT / "results/bipia/code_context_v1"
SIGNAL = Path(__file__).with_name("code_context_signal.py")


def samples() -> tuple[dict, list[dict]]:
    protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
    raw = (DATA / "samples.jsonl").read_bytes()
    if protocol["status"] != "FROZEN_BEFORE_SIGNAL_IMPLEMENTATION" or digest(raw) != protocol["samples_sha256"]:
        raise ValueError("Confirmation set is not the frozen pre-implementation version")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    if len(rows) != 300 or len({row["source_id"] for row in rows}) != 100:
        raise ValueError("Confirmation set size mismatch")
    old = {json.loads(line)["source_id"] for line in (PRIOR_DATA / "samples.jsonl").read_text(encoding="utf-8").splitlines()}
    if old & {row["source_id"] for row in rows}:
        raise ValueError("Confirmation sources overlap development or prior test sources")
    return protocol, rows


def key(row: dict) -> tuple:
    return row["source_id"], int(row["label"]), row["position"]


def summarize(rows: list[dict]) -> dict:
    return {name: rates(rows, name) for name in ("rule", "supervised", "comment", "rule_or_comment")}


def development() -> None:
    if (RESULTS / "selection.json").exists():
        raise FileExistsError("Development selection already frozen")
    prior = json.loads((PRIOR_DATA / "protocol.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (PRIOR_DATA / "samples.jsonl").read_text(encoding="utf-8").splitlines()
            if json.loads(line)["split"] == "development"]
    if digest((PRIOR_DATA / "samples.jsonl").read_bytes()) != prior["samples_sha256"]:
        raise ValueError("Prior development data hash mismatch")
    with (PRIOR_RESULTS / "predictions.csv").open(encoding="utf-8", newline="") as handle:
        old = {key(row): row for row in csv.DictReader(handle) if row["split"] == "development"}
    if len(rows) != 300 or len(old) != 300:
        raise ValueError("Development prediction count mismatch")
    predictions = []
    for row in rows:
        baseline = old[key(row)]
        comment = assess_comment_redirection(row["content"])["decision"] != "ALLOW"
        rule = baseline["rule"] == "True"
        predictions.append({"label": row["label"], "rule": rule,
                            "supervised": baseline["supervised"] == "True", "comment": comment,
                            "rule_or_comment": rule or comment})
    result = {"status": "FROZEN_BEFORE_CONFIRMATION", "candidate": "P1 OR Python-comment redirection",
              "signal_sha256": hashlib.sha256(SIGNAL.read_bytes()).hexdigest(),
              "development_data_sha256": prior["samples_sha256"],
              "confirmation_data_sha256": json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))["samples_sha256"],
              "development_metrics": summarize(predictions),
              "acceptance_constraint": "Research-only: compare detection and clean FPR; no automatic deployment"}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "selection.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def confirm() -> None:
    if (RESULTS / "summary.json").exists():
        raise FileExistsError("Confirmation results already exist; do not overwrite")
    selection = json.loads((RESULTS / "selection.json").read_text(encoding="utf-8"))
    protocol, rows = samples()
    if selection["status"] != "FROZEN_BEFORE_CONFIRMATION" or selection["signal_sha256"] != hashlib.sha256(SIGNAL.read_bytes()).hexdigest():
        raise ValueError("Selected signal changed after development")
    if selection["confirmation_data_sha256"] != protocol["samples_sha256"]:
        raise ValueError("Confirmation data differs from frozen selection")
    bundle, model_hash = _load(ARTIFACT.stat().st_mtime_ns, SELECTION.stat().st_mtime_ns)
    features = bundle["vectorizer"].transform(model_text(row["question"], row["content"]) for row in rows)
    scores = bundle["model"].predict_proba(features)[:, 1]
    predictions = []
    for row, score in zip(rows, scores):
        rule = detect_prompt_injection(row["content"]).decision != "ALLOW"
        comment = assess_comment_redirection(row["content"])["decision"] != "ALLOW"
        predictions.append({"source_id": row["source_id"], "label": row["label"],
                            "position": row["position"], "template_id": row["template_id"],
                            "rule": rule, "supervised": bool(score >= bundle["threshold"]),
                            "comment": comment, "rule_or_comment": rule or comment,
                            "supervised_score": float(score)})
    summary = {"status": "COMPLETE", "dataset_sha256": protocol["samples_sha256"],
               "signal_sha256": selection["signal_sha256"], "model_sha256": model_hash,
               "development_metrics": selection["development_metrics"],
               "confirmation_metrics": summarize(predictions),
               "limitations": ["Synthetic comments on one new codebase; not real agent attack success.",
                               "Templates are hand-written and variants share source files.",
                               "The researcher authored and knew confirmation templates before implementing the signal; not a blind test.",
                               "The candidate is research-only and has no tool-policy effect."]}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (RESULTS / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    lines = ["# Code 注释语境信号：开发与确认（探索性）", "",
             "候选方法为 P1 规则或通用注释重定向信号命中即复核。信号只读 Python 注释，不解析可执行代码。开发集使用上一轮标准库来源；确认集在信号实现前冻结，来自 100 个不同的 scikit-learn 文件及 8 种新措辞。未接入 P1/P3 授权。", "",
             "| 数据 | 方法 | 攻击检出率 | 干净误报率 | TP/FN | FP/TN |", "|---|---|---:|---:|---:|---:|"]
    for split, metrics in (("开发", selection["development_metrics"]), ("新来源确认", summary["confirmation_metrics"])):
        for name in ("rule", "supervised", "comment", "rule_or_comment"):
            item = metrics[name]
            lines.append(f"| {split} | {name} | {item['attack_detection_rate']:.2%} | {item['clean_fpr']:.2%} | {item['tp']}/{item['fn']} | {item['fp']}/{item['tn']} |")
    lines += ["", "## 解释边界", "", "本实验是合成代码注释的离线检测评估，不是真实 LLM 代理攻击成功率；只有一套新代码来源、100 条干净确认样本，误报率每条波动 1 个百分点。不要与 BIPIA Code 或上一轮标准库结果合并平均，也不要直接接入工具授权。", ""]
    (RESULTS / "report_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("development", "confirm"))
    mode = parser.parse_args().mode
    development() if mode == "development" else confirm()
