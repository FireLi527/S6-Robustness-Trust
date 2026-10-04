"""Fixed augmentation comparison on previously seen, family-held-out task pairs."""
from __future__ import annotations

from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression

from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.aggregation_data import native_development, reviewed_pairs, reviewed_maintenance
from s6.prompt_injection.boundary_protocol import family_folds, leakage_edges, source_threshold
from s6.prompt_injection.risk_aggregation import joint_matrix

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/boundary_transfer_v1"
SNAPSHOT = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
ARMS = ("native_content", "native_joint", "augmented_content", "augmented_joint")


def prepare() -> tuple[list[dict], list[dict], dict]:
    """Freeze inputs, family assignments and all model decisions before encoding."""
    native, reviewed, maintenance = native_development(ROOT), reviewed_pairs(ROOT), reviewed_maintenance(ROOT)
    edges = leakage_edges(native + reviewed)
    folds = family_folds(native, reviewed, edges)
    previous = read_json(ROOT / "results/bipia/risk_aggregation_v1/protocol.json")
    protected = {**previous["protected_sha256"], **previous["code_sha256"], **previous["input_sha256"]}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    files = [Path(__file__), ROOT / "s6/prompt_injection/boundary_protocol.py"]
    protocol = {"experiment": "boundary-transfer-v1", "seed": 2026, "arms": ARMS,
                "protected_sha256": protected,
                "code_sha256": {p.relative_to(ROOT).as_posix(): file_sha256(p) for p in files},
                "input_sha256": previous["input_sha256"], "source_licenses": previous["source_licenses"],
                "folds": folds, "leakage_edges": edges,
                "split_rule": "sorted family cyclic leave-one-out; next family calibration; remaining four training; normalized exact task/shared group/character similarity>=.88 edges cannot cross partitions",
                "training": "C=1 balanced liblinear logistic regression, max_iter=2000, seed=2026; native89 vs native89+reviewed24; identical encoding; no hyperparameter search",
                "encoding": "frozen local MiniLM, 256-token complete windows, overlap32, inverse-overlap weighted mean; no risk-max arm",
                "calibration": "native29 + held-in reviewed6, each source FPR<=5%; maximize pooled recall, tie lower pooled FPR then higher threshold; no evaluation labels used",
                "primary": "augmented_joint versus native_joint: held-out reviewed18 benign FPR and18 attack recall; content models are task-feature controls",
                "secondary": "fixed0.5 predictions; maintenance30 content-only across six models as correlated seen diagnostics, not180 independent samples",
                "stop_rule": "one fixed six-fold comparison; no tuning after held-out scoring; no deployment or independent-generalization claim",
                "exposure": "All native development/reviewed/maintenance examples previously seen in research. Cross-validation is only within-run separation, not a fresh independent test.",
                "test_policy": "native original test excluded; external no-task data never assigned invented tasks"}
    return native + reviewed, maintenance, protocol


def encode(encoder: LocalTextEncoder, rows: list[dict]) -> dict[str, dict]:
    """Return complete document embeddings and separately recorded task coverage."""
    records = {}
    for row in rows:
        content, content_stats = encoder.encode_one(row["content"])
        task, task_stats = encoder.encode_one(row["task"]) if row.get("task") is not None else (None, None)
        records[row["id"]] = {"content": content, "task": task, "label": row["label"],
                               "coverage": {"id": row["id"], "content": content_stats, "task": task_stats}}
    return records


def matrix(records: dict[str, dict], identifiers: list[str], feature: str) -> np.ndarray:
    """Assemble content or task-conditioned vectors by explicit fold identifiers."""
    content = np.stack([records[key]["content"] for key in identifiers])
    if feature == "content":
        return content
    if feature != "joint" or any(records[key]["task"] is None for key in identifiers):
        raise ValueError("Joint features require original tasks")
    return joint_matrix(np.stack([records[key]["task"] for key in identifiers]), content)


def fit_fold(records: dict[str, dict], fold: dict) -> tuple[dict, dict]:
    """Fit all four arms and freeze source-constrained thresholds without evaluation."""
    models, selection = {}, {}
    calibration = fold["native_calibration"] + fold["reviewed_calibration"]
    labels = np.array([records[key]["label"] for key in calibration])
    sources = np.array(["native"] * len(fold["native_calibration"]) + ["reviewed"] * len(fold["reviewed_calibration"]))
    for arm in ARMS:
        feature = arm.split("_")[1]
        identifiers = fold["native_train"] + (fold["reviewed_train"] if arm.startswith("augmented") else [])
        model = LogisticRegression(C=1, class_weight="balanced", solver="liblinear", random_state=2026, max_iter=2000)
        model.fit(matrix(records, identifiers, feature), [records[key]["label"] for key in identifiers])
        scores = model.predict_proba(matrix(records, calibration, feature))[:, 1]
        threshold, metrics = source_threshold(labels, scores, sources)
        selection[arm] = {"threshold": threshold, "calibration": metrics, "training_ids": identifiers,
                          "calibration_predictions": [{"id": key, "label": int(label), "source": str(source), "score": float(score)}
                                                      for key, label, source, score in zip(calibration, labels, sources, scores)]}
        models[arm] = model
        write_json(OUT / f'fold{fold["fold"]}_{arm}_classifier.json',
                   {"coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(), "classes": model.classes_.tolist()})
    return models, selection


def predict(records: dict[str, dict], identifiers: list[str], model, feature: str,
            threshold: float, fold: int) -> list[dict]:
    """Score after calibration; retain both selected and prespecified 0.5 decisions."""
    scores = model.predict_proba(matrix(records, identifiers, feature))[:, 1]
    return [{"id": key, "fold": fold, "label": records[key]["label"], "score": float(score),
             "threshold": threshold, "flag": bool(score >= threshold), "fixed05": bool(score >= .5)}
            for key, score in zip(identifiers, scores)]


def summarize(predictions: list[dict], flag: str = "flag") -> dict:
    """Counts use document labels; pooled cross-fold observations remain dependent."""
    return binary_metrics(np.array([r["label"] for r in predictions]), np.array([r[flag] for r in predictions]))


def report(summary: dict) -> None:
    """Publish all arms, rather than choosing a winner after seeing held-out labels."""
    lines = ["# 任务边界补充训练：分家族开发对照", "", "六折：每折评估1个家族6条，校准1个家族6条，另4个家族24条可用于补充训练。原生训练89条、原生校准29条；原测试集不评分。", "",
             "同一冻结MiniLM全文256窗口表示，比较是否补充数据及是否加入原始任务。校准对原生和审核来源分别限制经验误报率≤5%；只有6和3条正常校准样本，不是总体误报保证。", "",
             "## 家族留出结果（已见开发材料）", "", "|方案|检出/18|误报/18|准确率|精确率|召回率|误报率|", "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        m = summary["heldout"][arm]["calibrated"]
        precision = "未定义" if m["precision"] is None else f'{m["precision"]:.2%}'
        lines.append(f'|{arm}|{m["tp"]}|{m["fp"]}|{m["accuracy"]:.2%}|{precision}|{m["recall"]:.2%}|{m["fpr"]:.2%}|')
    lines += ["", "所有数据以前已用于开发；分组留出只保证本次单折不混用，不能消除历史观察造成的选择偏差。各折训练集重叠，不把六折视为独立重复，也不与上一轮不同阈值/划分的准确率直接排名。", "",
              "维护文本没有原始任务，仅报告正文模型；每条被六个折模型评分，不能当作180条独立数据。固定0.5结果、每折阈值/校准样本及维护诊断详见summary.json和selection.json。", "",
              "本轮不做新增文本标注，不用模型预测代替人工标签，不改前端默认模型或工具权限。具体复核结论见findings_ZH.md。"]
    atomic_binary(OUT / "report_ZH.md", lambda stream: stream.write(("\n".join(lines) + "\n").encode()))


def main() -> None:
    rows, maintenance, protocol = prepare()
    with new_run(OUT, protocol):
        encoder = LocalTextEncoder(SNAPSHOT, OUT / "cache", EncodingConfig())
        write_json(OUT / "encoder.json", encoder.metadata)
        records = encode(encoder, rows + maintenance)
        write_json(OUT / "coverage.json", [r["coverage"] for r in records.values()])
        models, selections = {}, {}
        for fold in protocol["folds"]:
            models[fold["fold"]], selections[str(fold["fold"])] = fit_fold(records, fold)
        write_json(OUT / "selection.json", selections)
        print("All six folds calibrated; held-out scoring starts now", flush=True)
        heldout, diagnostic = {arm: [] for arm in ARMS}, {arm: [] for arm in ARMS if arm.endswith("content")}
        for fold in protocol["folds"]:
            for arm in ARMS:
                model, threshold = models[fold["fold"]][arm], selections[str(fold["fold"])][arm]["threshold"]
                heldout[arm].extend(predict(records, fold["evaluation"], model, arm.split("_")[1], threshold, fold["fold"]))
                if arm in diagnostic:
                    diagnostic[arm].extend(predict(records, [r["id"] for r in maintenance], model, "content", threshold, fold["fold"]))
        write_json(OUT / "heldout_predictions.json", heldout)
        write_json(OUT / "maintenance_predictions.json", diagnostic)
        summary = {"heldout": {arm: {"calibrated": summarize(rows), "fixed05": summarize(rows, "fixed05"),
                                      "per_fold": {str(i): summarize([r for r in rows if r["fold"] == i]) for i in range(6)}}
                               for arm, rows in heldout.items()},
                   "maintenance_seen_correlated": {arm: {"pooled_180_decisions_not_independent": summarize(rows),
                                                           "per_fold": {str(i): summarize([r for r in rows if r["fold"] == i]) for i in range(6)}}
                                                    for arm, rows in diagnostic.items()},
                   "independent_test": False, "deployed": False}
        write_json(OUT / "summary.json", summary)
        report(summary)
        for name, digest in protocol["protected_sha256"].items():
            require_hash(ROOT / name, digest)
    print(f"COMPLETE: {OUT}", flush=True)


if __name__ == "__main__":
    main()
