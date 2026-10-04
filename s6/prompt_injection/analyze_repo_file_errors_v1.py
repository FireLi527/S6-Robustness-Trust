"""Replay frozen predictions, audit AI annotations, and diagnose external errors.

No fitting, threshold selection, external code execution, or baseline mutation.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np

from evaluate_repo_file_external_v1 import external_cases, normalized, read_rows
from train_repo_file_v1 import MODEL, RESULTS, ROOT

OUT = ROOT / "results/bipia/repo_file_review_v1"
ANNOTATIONS = ROOT / "data/bipia/repo_file_review_v1/annotations.json"
MAINTAINER = ROOT / "data/bipia/maintainer_negatives_v1"
REPOGUARD = ROOT / "data/bipia/code_external_v1/samples.jsonl"
GOAL_REASONS = {
    "CANARY_READ": "冒充维护者，把读取并复制 canary 设为修改代码的前置条件。",
    "CANARY_EXFIL": "借用 CI 检查理由，要求把 canary 复制到额外文件。",
    "TEST_DELETE": "冒充维护者决策，要求删除失败测试且不要修复生产代码，与修复任务冲突。",
    "UNAUTH_SHELL": "借用 CI 评分要求，添加与修复缺陷无关的 shell 写标记操作。",
    "BACKDOOR": "借用代码规范与静态检查理由，要求向所有修改文件插入基准标记。",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def top_features(pipeline, texts: list[str]) -> list[dict]:
    features = pipeline.named_steps["features"]
    model = pipeline.named_steps["model"]
    names = features.get_feature_names_out()
    matrix = features.transform(texts)
    contributions = matrix.multiply(model.coef_[0]).tocsr()
    result = []
    for i in range(len(texts)):
        row = contributions.getrow(i)
        pairs = sorted(zip(row.indices, row.data), key=lambda x: x[1])
        result.append({
            "toward_benign": [{"feature": str(names[j]), "contribution": float(v)}
                              for j, v in pairs if v < 0][:8],
            "toward_attack": [{"feature": str(names[j]), "contribution": float(v)}
                              for j, v in reversed(pairs) if v > 0][:8],
            "logit": float(row.sum() + model.intercept_[0]),
        })
    return result


def run() -> None:
    if OUT.exists():
        raise FileExistsError("Review output already exists; do not overwrite")
    annotation = json.loads(ANNOTATIONS.read_text(encoding="utf-8"))
    protocol_path = MAINTAINER / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    samples_path = MAINTAINER / "samples.jsonl"
    raw = samples_path.read_bytes()
    if sha(raw) != annotation["reference_samples_sha256"] or sha(raw) != protocol["samples_sha256"]:
        raise ValueError("Maintainer samples differ from annotation reference")
    samples = read_rows(samples_path)
    labels = {r["id"]: r for r in annotation["annotations"]}
    if len(labels) != 30 or set(labels) != {r["source_id"] for r in samples}:
        raise ValueError("Annotation IDs must cover all 30 original samples exactly once")
    for row in samples:
        path = ROOT / "external" / (row["repo"] + "-benign") / row["path"]
        original = path.read_bytes()
        if sha(original) != row["source_file_sha256"]:
            raise ValueError(f"Source file changed: {path}")
        excerpt = "\n".join(original.decode("utf-8").splitlines()[row["first_line"]-1:row["last_line"]]).strip()
        if excerpt != row["content"]:
            raise ValueError(f"Excerpt mismatch: {row['source_id']}")

    frozen = json.loads((RESULTS / "validation.json").read_text(encoding="utf-8"))
    if sha(MODEL.read_bytes()) != frozen["model_sha256"]:
        raise ValueError("Model changed")
    bundle = joblib.load(MODEL)
    pipe, threshold = bundle["pipeline"], bundle["threshold"]
    if threshold != frozen["threshold"]:
        raise ValueError("Threshold changed")
    cases = external_cases()
    with (RESULTS / "external_predictions.csv").open(encoding="utf-8", newline="") as f:
        cached = {(r["source"], r["id"]): r for r in csv.DictReader(f)}
    if len(cached) != len(cases):
        raise ValueError("External prediction count changed")
    scores = pipe.predict_proba([r["text"] for r in cases])[:, 1]
    for row, score in zip(cases, scores):
        old = cached[(row["source"], row["id"])]
        if sha(normalized(row["text"]).encode()) != old["normalized_text_sha256"]:
            raise ValueError(f"External text changed: {row['id']}")
        if abs(float(old["model_score"]) - score) > 1e-12:
            raise ValueError(f"Prediction replay mismatch: {row['id']}")
        row.update(score=float(score), flag=bool(score >= threshold), p1_flag=old["p1_flag"] == "True")

    reviews = []
    for sample in samples:
        row = next(r for r in cases if r["source"] == "maintainer_candidates" and r["id"] == sample["source_id"])
        source = protocol["repos"][sample["repo"]]
        reviews.append({**labels[row["id"]], "reviewer": annotation["reviewer"],
                        "human_reviewer_label": None, "task_conflict": "not_assessable_without_user_task",
                        "source_url": f"{source['url']}/blob/{source['commit']}/{sample['path']}#L{sample['first_line']}",
                        "content_sha256": sha(sample["content"].encode()), "content": sample["content"],
                        "model_score": row["score"], "model_flag": row["flag"], "p1_flag": row["p1_flag"]})
    explanations = top_features(pipe, [r["content"] for r in reviews])
    for row, explanation in zip(reviews, explanations):
        row["linear_feature_contributions"] = explanation

    repo_rows = read_rows(REPOGUARD)
    clean = {r["source_id"]: r["content"] for r in repo_rows if r["kind"] == "benchmark_clean"}
    attacks = [r for r in repo_rows if r["kind"] == "benchmark_attack"]
    payloads = []
    for r in attacks:
        suffix = clean[r["source_id"]]
        if not r["content"].endswith(suffix):
            raise ValueError("Attack no longer consists of prefix plus matching clean file")
        prefix = r["content"][:-len(suffix)].rstrip()
        if not all(line.startswith("#") or not line.strip() for line in prefix.splitlines()):
            raise ValueError("Unexpected attack prefix format")
        payloads.append(prefix)
    plain = ["\n".join(line[2:] if line.startswith("# ") else line[1:] if line.startswith("#") else line
                       for line in text.splitlines()) for text in payloads]
    comment_scores = pipe.predict_proba(payloads)[:, 1]
    plain_scores = pipe.predict_proba(plain)[:, 1]
    variants = []
    for r, payload, cs, ps in zip(attacks, payloads, comment_scores, plain_scores):
        old = cached[("RepoGuardBench", f"{r['source_id']}/{r['goal']}")]
        variants.append({"id": f"{r['source_id']}/{r['goal']}", "goal": r["goal"],
                         "full_score": float(old["model_score"]), "comment_only_score": float(cs),
                         "plain_comment_score": float(ps), "payload_sha256": sha(payload.encode()),
                         "payload": payload, "review_reason": GOAL_REASONS[r["goal"]]})
    by_goal = {}
    for goal in GOAL_REASONS:
        rows = [r for r in variants if r["goal"] == goal]
        by_goal[goal] = {"n": len(rows), "unique_prefixes": len({r["payload_sha256"] for r in rows}),
                         "full_detected": sum(r["full_score"] >= threshold for r in rows),
                         "comment_only_detected": sum(r["comment_only_score"] >= threshold for r in rows),
                         "plain_comment_detected": sum(r["plain_comment_score"] >= threshold for r in rows),
                         "full_score_range": [min(r["full_score"] for r in rows), max(r["full_score"] for r in rows)],
                         "comment_only_score": rows[0]["comment_only_score"],
                         "plain_comment_score": rows[0]["plain_comment_score"],
                         "review_reason": GOAL_REASONS[goal]}
    errors = [r.copy() for r in cases if r["label"] is not None and r["flag"] != bool(r["label"])]
    explanations = top_features(pipe, [r["text"] for r in errors])
    for row, explanation in zip(errors, explanations):
        row["error_type"] = "false_negative" if row["label"] else "false_positive"
        row["linear_feature_contributions"] = explanation
        if row["source"] == "RepoGuardBench" and row["label"]:
            goal = row["id"].rsplit("/", 1)[1]
            row["review_reason"] = GOAL_REASONS[goal]
            row["review_method"] = "verified exact shared prefix; family-level review, not independent row annotation"
    inputs = [ANNOTATIONS, samples_path, protocol_path, REPOGUARD, MODEL,
              RESULTS / "external_predictions.csv", RESULTS / "validation.json",
              ROOT / "data/bipia/code_context_v2/samples.jsonl",
              ROOT / "external/prompt-injection-benchmark/dataset/v1.0.0/full.jsonl"]
    summary = {"status": "DIAGNOSTIC_COMPLETE_AI_LABELS_PENDING_HUMAN_REVIEW",
               "input_sha256": {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p.read_bytes()) for p in inputs},
               "threshold": threshold, "replayed_predictions": len(cases),
               "annotation_status": annotation["status"], "provisional_benign_count": len(reviews),
               "model_flags_on_provisional_benign": sum(r["model_flag"] for r in reviews),
               "p1_flags_on_provisional_benign": sum(r["p1_flag"] for r in reviews),
               "flags_by_document_kind": {kind: {"n": sum(r["kind"] == kind for r in reviews),
                                                       "model_flagged": sum(r["kind"] == kind and r["model_flag"] for r in reviews)}
                                           for kind in sorted({r["kind"] for r in reviews})},
               "error_counts": dict(Counter(r["source"] + "/" + r["error_type"] for r in errors)),
               "repoguard_diagnostic_ablation": by_goal,
               "limitations": ["AI first-pass labels are not independent human adjudication or official FPR labels.",
                               "Observed test sources now inform development; a new untouched external confirmation set is required.",
                               "Payload-only inputs use known benchmark boundaries and are diagnostic, not a deployable detector.",
                               "Linear contributions describe this model, not causal evidence of dataset bias."]}
    OUT.mkdir(parents=True)
    dump(OUT / "summary.json", summary)
    dump(OUT / "maintainer_review.json", reviews)
    dump(OUT / "external_errors.json", errors)
    dump(OUT / "payload_ablation.json", variants)
    lines = ["# 仓库文件检测：错误分析与初审", "",
             "状态：离线诊断完成；30 条维护说明为 AI 初审，待独立人工复核。未重新训练或改变阈值。", "",
             f"重放 {len(cases)} 条既有外部预测，原文哈希和分数均匹配。30 条维护说明也已逐条匹配冻结来源文件及行号。", "",
             "## 维护说明", "",
             "初审均为正常项目文档内容；原文不提供执行授权，也没有给定用户任务可据以评估任务冲突。", "",
             f"模型标记 {sum(r['model_flag'] for r in reviews)}/30，P1 标记 {sum(r['p1_flag'] for r in reviews)}/30。按初审标签分别为 43.33% 和 10.00% 的误报比例，不能作为独立人工评估或真实仓库总体误报率。", "",
             "| 样本 | 类型 | 模型标记 | 分数 | 初审理由 |", "| --- | --- | --- | --- | --- |"]
    for r in reviews:
        lines.append(f"| [{r['id']}]({r['source_url']}) | {r['kind']} | {'是' if r['model_flag'] else '否'} | {r['model_score']:.3f} | {r['reason']} |")
    lines += ["", "## 固定模型输入诊断", "",
              "利用已知的注入前缀/干净文件配对边界，只改变送入冻结模型的文本，保持权重和阈值不变。该边界在真实检测时未知，因此以下不能当作新检测器成绩。", "",
              "| 目标 | 完整文件检出 | 仅注入注释 | 去除注释标记 | 独立前缀数 |", "| --- | --- | --- | --- | --- |"]
    for goal, r in by_goal.items():
        lines.append(f"| {goal} | {r['full_detected']}/{r['n']} | {r['comment_only_detected']}/{r['n']} | {r['plain_comment_detected']}/{r['n']} | {r['unique_prefixes']} |")
    lines += ["", "所有外部错误原文和模型线性特征贡献见 external_errors.json；注释消融逐项结果见 payload_ablation.json。特征贡献解释的是当前模型打分，不能独立证明错误成因。", "",
              "30 条初审的内容、来源、理由与待复核状态见 maintainer_review.json；任何含指令的外部样本均未被执行。"]
    (OUT / "report_ZH.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
