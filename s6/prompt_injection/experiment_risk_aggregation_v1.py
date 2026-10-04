"""Predeclared development experiment; no test scoring or default-model changes."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics, calibrate_threshold
from s6.engineering.text_embeddings import EncodingConfig
from s6.engineering.window_embeddings import WindowTextEncoder, pooled_document
from s6.prompt_injection.aggregation_data import native_development, reviewed_pairs, reviewed_maintenance, maintenance_stress
from s6.prompt_injection.risk_aggregation import ARMS, aggregate_scores, joint_matrix

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/risk_aggregation_v1"
SNAPSHOT = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FEATURES = ("content", "joint")


def inputs_and_protocol() -> tuple[list[dict], dict, dict]:
    """Record protocol and guards before any model fitting or diagnostic scoring."""
    native = native_development(ROOT)
    diagnostics = {"reviewed36_seen": reviewed_pairs(ROOT), "maintenance30_seen": reviewed_maintenance(ROOT)}
    paths = ["data/bipia/native_pairs_v1/samples.json", "data/bipia/native_pairs_v1/protocol.json",
             "data/bipia/repo_file_v2/candidate_batch1.json", "data/bipia/repo_file_v2/candidate_batch2.json",
             "data/bipia/repo_file_v2/human_review_completion.json", "data/bipia/maintainer_negatives_v1/samples.jsonl",
             "data/bipia/maintainer_negatives_v1/protocol.json", "data/bipia/repo_file_review_v1/human_review_final.json"]
    dependencies = [Path(__file__), ROOT / "s6/prompt_injection/aggregation_data.py",
                    ROOT / "s6/prompt_injection/risk_aggregation.py", ROOT / "s6/engineering/window_embeddings.py",
                    ROOT / "s6/engineering/text_embeddings.py", ROOT / "s6/engineering/artifacts.py",
                    ROOT / "s6/engineering/metrics.py"]
    protected = read_json(ROOT / "s6/engineering/frozen_assets.json")["files"]
    protected = {**protected, **read_json(ROOT / "results/bipia/long_text_v1/protocol.json")["code_sha256"]}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    protocol = {"experiment": "risk-aggregation-v1", "seed": 2026,
                "input_sha256": {name: file_sha256(ROOT / name) for name in paths},
                "code_sha256": {p.relative_to(ROOT).as_posix(): file_sha256(p) for p in dependencies},
                "protected_sha256": protected, "primary_window": 256, "sensitivity_window": 128,
                "window_sizes": [256, 128], "overlap_tokens": 32, "top_k": 2,
                "arms": list(ARMS), "features": list(FEATURES),
                "training": "89 native train documents; one C=1 balanced liblinear logistic classifier per window size/feature; document vectors only; no inherited chunk labels",
                "aggregation": "full_mean=classifier(normalized weighted document mean); max_window=max probability; top2_mean=mean of highest min(2,n) window probabilities; same classifier for all three",
                "calibration": "29 native validation docs; per-arm maximize recall under empirical FPR<=5%, tie lower FPR then higher threshold",
                "selection": "primary 256 only, within each feature: higher validation recall, lower FPR, then ARMS order; sensitivity 128 not a second model search",
                "diagnostics": "36 previously reviewed pairs; 30 reviewed maintenance excerpts content-only; 3 derived long maintenance fixtures; score after all thresholds freeze; do not recalibrate",
                "stress_recipe": "concatenate benign excerpts within each repository in source order; repeat with paragraph separators until >=768 tokens; labels inherited, not new human review",
                "command_slice": "deterministic content markers ::, ```, >>>, pytest, python, pip, tox, git; not independent semantic labels",
                "source_licenses": {"native": "AgentInjectionBench Apache-2.0 at native_pairs_v1 recorded revision",
                                    "maintenance": read_json(ROOT / "data/bipia/maintainer_negatives_v1/protocol.json")["repos"],
                                    "reviewed36": "project-authored synthetic, single-user reviewed"},
                "stop_rule": "one fixed development comparison; no new data search or tuning on diagnostics; conclude even with no gain",
                "test_policy": "native test rows filtered before encoding/training/scoring; no independent test available",
                "deployment": False}
    return native, diagnostics, protocol


def encode_rows(encoder: WindowTextEncoder, rows: list[dict]) -> list[dict]:
    records = []
    for row in rows:
        vectors, weights, stats = encoder.encode_windows(row["content"])
        task = encoder.encode_one(row["task"])[0] if row.get("task") is not None else None
        records.append({"row": row, "windows": vectors, "document": pooled_document(vectors, weights),
                        "task": task, "coverage": stats})
    return records


def matrices(records: list[dict], feature: str) -> np.ndarray:
    content = np.stack([r["document"] for r in records])
    if feature == "content":
        return content
    return joint_matrix(np.stack([r["task"] for r in records]), content)


def score_documents(model, records: list[dict], feature: str) -> list[dict]:
    full = model.predict_proba(matrices(records, feature))[:, 1]
    scored = []
    for record, full_score in zip(records, full):
        windows = record["windows"]
        if feature == "joint":
            windows = joint_matrix(np.repeat(record["task"][None, :], len(windows), axis=0), windows)
        scores = model.predict_proba(windows)[:, 1]
        scored.append({"id": record["row"]["id"], "label": record["row"]["label"],
                       "scores": aggregate_scores(float(full_score), scores),
                       "window_scores": scores.tolist(), "winning_window": int(np.argmax(scores)),
                       "coverage": record["coverage"]})
    return scored


def fit_and_calibrate(encoder: WindowTextEncoder, rows: list[dict], width: int) -> tuple[dict, dict]:
    records = encode_rows(encoder, rows)
    train = [r for r in records if r["row"]["split"] == "train"]
    val = [r for r in records if r["row"]["split"] == "validation"]
    labels = np.array([r["row"]["label"] for r in val])
    models, selections = {}, {}
    write_json(OUT / f"w{width}_development_coverage.json",
               [{"id": r["row"]["id"], "split": r["row"]["split"], **r["coverage"]} for r in records])
    for feature in FEATURES:
        model = LogisticRegression(C=1, class_weight="balanced", solver="liblinear", random_state=2026, max_iter=2000)
        model.fit(matrices(train, feature), [r["row"]["label"] for r in train])
        predictions = score_documents(model, val, feature)
        write_json(OUT / f"w{width}_{feature}_validation_predictions.json", predictions)
        selections[feature] = {}
        for arm in ARMS:
            scores = np.array([r["scores"][arm] for r in predictions])
            threshold, metrics = calibrate_threshold(labels, scores)
            selections[feature][arm] = {"threshold": threshold, "validation": metrics,
                                        "fixed_05": binary_metrics(labels, scores >= .5)}
        models[feature] = model
        write_json(OUT / f"w{width}_{feature}_classifier.json",
                   {"coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(), "classes": model.classes_.tolist()})
    return models, selections


def diagnostic_scores(encoder: WindowTextEncoder, models: dict, selections: dict,
                      diagnostics: dict, width: int) -> tuple[dict, list[dict]]:
    summaries, failures = {}, []
    for name, rows in diagnostics.items():
        records = encode_rows(encoder, rows)
        labels = np.array([r["label"] for r in rows])
        summaries[name] = {"samples": len(rows), "multiwindow": sum(len(r["windows"]) > 1 for r in records), "features": {}}
        available = FEATURES if all(r.get("task") is not None for r in rows) else ("content",)
        for feature in available:
            predictions = score_documents(models[feature], records, feature)
            write_json(OUT / f"w{width}_{name}_{feature}_predictions.json", predictions)
            summaries[name]["features"][feature] = {}
            for arm in ARMS:
                threshold = selections[feature][arm]["threshold"]
                flags = np.array([r["scores"][arm] >= threshold for r in predictions])
                metrics = binary_metrics(labels, flags)
                summaries[name]["features"][feature][arm] = metrics
                for row, prediction, flag in zip(rows, predictions, flags):
                    if row["label"] == 0 and flag:
                        failures.append({"window": width, "source": name, "feature": feature, "arm": arm,
                                         "id": row["id"], "score": prediction["scores"][arm], "threshold": threshold,
                                         "winning_window": prediction["winning_window"], "content": row["content"],
                                         "label_basis": "existing review or declared derived-fixture label"})
                command_mask = np.array([bool(r.get("has_command_marker")) for r in rows])
                if command_mask.any():
                    metrics["command_marker_slice"] = binary_metrics(labels[command_mask], flags[command_mask])
    return summaries, failures


def write_report(summary: dict) -> None:
    lines = ["# 分块风险聚合：开发实验", "", "状态：单轮固定方案完成。没有新独立测试，不替换前端模型。",
             "", "## 方案", "", "同一模型只按训练文档拟合，不给攻击文档的每个分块强行标攻击。全文均值先聚合向量再打分；最高块和前两块均值使用该模型的分块概率。256-token为主对照，128-token完整分块为预先固定的敏感性检查；重叠32，均不截断正文。",
             "", "训练89条；验证29条（23攻击、6正常）。每种聚合仅在验证集校准经验误报率≤5%的阈值；已见诊断集不用于再选阈值。全文均值与最高风险并非同一种统计量，因此各自校准。", "",
             "## 验证结果", "", "|窗口|特征|聚合|检出/23|误报/6|准确率|", "|---|---|---|---:|---:|---:|"]
    for width, block in summary["selection"].items():
        for feature, arms in block.items():
            for arm, item in arms.items():
                m = item["validation"]
                lines.append(f'|{width}|{feature}|{arm}|{m["tp"]}|{m["fp"]}|{m["accuracy"]:.2%}|')
    lines += ["", "## 正常维护文本诊断（仅正文模型）", "", "|窗口|集合|样本数|多块文档|全文均值误报|最高块误报|前两块误报|", "|---|---|---:|---:|---:|---:|---:|"]
    for width, datasets in summary["diagnostics"].items():
        for name in ("maintenance30_seen", "maintenance3_derived_long"):
            block = datasets[name]
            errors = [str(block["features"]["content"][arm]["fp"]) for arm in ARMS]
            lines.append(f'|{width}|{name}|{block["samples"]}|{block["multiwindow"]}|' + "|".join(errors) + "|")
    lines += ["", "维护文本没有原始用户任务，因此不补造任务，也不报告联合模型结果。30条是此前经一位用户审核的开发难负例；3条长文本是按仓库拼接/重复这些材料形成的派生压力用例，不是3个新独立样本。引用命令标记子集的分母与误报见summary.json。",
              "", "## 解释边界", "", "验证集正常样本仅6条，0误报不是总体5%误报保证。相同文档/高度重叠窗口不是独立观测。分块分类器未做分块级监督，其分数可能与整篇训练分布不同。最高分随窗口数量增加可能放大误报。",
              "36条已见任务配对仅作跨来源开发诊断，保留逐条结果；没有新独立测试、统计显著性或真实代理攻击成功率结论。128-token窗口是完整覆盖，不是恢复128截断。",
              "本次按停止规则一次完成；未依据诊断失败追加规则或调阈值。后续需要新的独立来源与充分正常样本才能判断泛化；不无限搜集数据延长本实验。",
              "", "协议、来源/标签哈希、编码器元数据、逐块分数、覆盖统计、分类器系数和误报正文均保存在本目录；具体结论见后续核验的findings_ZH.md。"]
    from s6.engineering.artifacts import atomic_binary
    atomic_binary(OUT / "report_ZH.md", lambda stream: stream.write(("\n".join(lines)+"\n").encode()))


def main() -> None:
    native, diagnostics, protocol = inputs_and_protocol()
    with new_run(OUT, protocol):
        encoders, models, selections = {}, {}, {}
        for width in protocol["window_sizes"]:
            encoder = WindowTextEncoder(SNAPSHOT, OUT / "cache", EncodingConfig(window_tokens=width))
            encoders[width] = encoder
            write_json(OUT / f"w{width}_encoder.json", {**encoder.metadata, "window_code_sha256": file_sha256(ROOT / "s6/engineering/window_embeddings.py")})
            models[width], selections[str(width)] = fit_and_calibrate(encoder, native, width)
            print(f"Fit and calibrated window={width}; no diagnostic scoring yet", flush=True)
        winners = {feature: max(ARMS, key=lambda arm: (selections["256"][feature][arm]["validation"]["recall"],
                                                      -selections["256"][feature][arm]["validation"]["fpr"],
                                                      -ARMS.index(arm))) for feature in FEATURES}
        write_json(OUT / "selection.json", {"by_window": selections, "primary_choices": winners})
        diagnostics["maintenance3_derived_long"] = maintenance_stress(diagnostics["maintenance30_seen"], encoders[256].tokenizer)
        write_json(OUT / "derived_fixtures.json", diagnostics["maintenance3_derived_long"])
        summary = {"selection": selections, "primary_choices": winners, "diagnostics": {}, "test_scored": False}
        failures = []
        for width, encoder in encoders.items():
            scored, errors = diagnostic_scores(encoder, models[width], selections[str(width)], diagnostics, width)
            summary["diagnostics"][str(width)] = scored
            failures.extend(errors)
        write_json(OUT / "false_positives.json", failures)
        write_json(OUT / "summary.json", summary)
        write_report(summary)
        for name, digest in protocol["protected_sha256"].items():
            require_hash(ROOT / name, digest)
        print(f"COMPLETE: {OUT}; primary development choices={winners}", flush=True)


if __name__ == "__main__":
    main()
