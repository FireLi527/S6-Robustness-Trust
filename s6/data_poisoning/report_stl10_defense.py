"""Score frozen selections and validate completed defense/control training."""
from pathlib import Path
import csv
import json
import hashlib
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dataset_config import DATA_ROOT, RESULTS_ROOT, IMAGE_ROOT
from prepare_stl10_defense import DEFENSE_ROOT, sha, DATASETS
from manifest_protocol import load_candidate_manifest, load_hidden_ground_truth, validate_candidate_truth_pair


def validate_run(s):
    assert s["status"] == "COMPLETE" and Path(s["checkpoint"]).is_file()
    assert sha(Path(s["manifest"])) == s["manifest_sha256"]
    assert sha(IMAGE_ROOT / "val.txt") == s["validation_split_sha256"]
    assert sha(IMAGE_ROOT / "test.txt") == s["test_split_sha256"]
    with (Path(s["result_dir"]) / "history.csv").open(encoding="utf-8-sig") as f:
        history = list(csv.DictReader(f))
    assert len(history) == 20
    with (Path(s["result_dir"]) / "test_predictions.csv").open(encoding="utf-8-sig") as f:
        predictions = list(csv.DictReader(f))
    assert len(predictions) == 8000
    correct = sum(r["true_label"] == r["predicted_label"] for r in predictions)
    source = [r for r in predictions if r["true_label"] == "0"]
    assert len(source) == 800
    target_errors = sum(r["predicted_label"] == "1" for r in source)
    assert abs(correct / 8000 - s["test"]["accuracy"]) < 1e-6
    assert abs(target_errors / 800 - s["test"]["targeted_0_to_1_rate"]) < 1e-6
    from sklearn.metrics import f1_score
    assert abs(f1_score([r["true_label"] for r in predictions], [r["predicted_label"] for r in predictions], average="macro") - s["test"]["macro_f1"]) < 1e-6


def main():
    root = RESULTS_ROOT / "defense_training"
    plan_path = DEFENSE_ROOT / "selection_plan.json"
    plan = json.loads(plan_path.read_text())
    trained = json.loads((root / "defense_results.json").read_text())
    assert trained["completed_runs"] == trained["expected_runs"] == 8
    assert trained["selection_plan_sha256"] == sha(plan_path)
    baseline = json.loads((RESULTS_ROOT / "model_training" / "comparison_summary.json").read_text())
    untreated = {s["dataset"]: s for s in baseline["summaries"]}
    variants = {s["dataset"]: s for s in trained["summaries"]}
    assert set(variants) == set(plan["variants"])
    for s in [*untreated.values(), *variants.values()]:
        validate_run(s)
    rows = []
    # Hidden truth is opened only here, AFTER selections and models are frozen.
    for dataset in DATASETS:
        source_rows = load_candidate_manifest(DATA_ROOT / "manifests" / f"{dataset}.csv")
        truth = validate_candidate_truth_pair(source_rows, load_hidden_ground_truth(DATA_ROOT / "hidden_ground_truth" / f"{dataset}.csv"))
        source_by_id = {r["sample_id"]: r for r in source_rows}
        original_poison = {sid for sid,r in truth.items() if r["poisoned"].lower() == "true"}
        for strategy in ("untreated", "random", "semantic"):
            if strategy == "untreated":
                s = untreated[dataset]; removed = set(); kept_rows = source_rows
            else:
                name = f"{dataset}__{strategy}"
                s = variants[name]; v = plan["variants"][name]
                manifest_path = DEFENSE_ROOT / "manifests" / f"{name}.csv"
                assert sha(manifest_path) == v["manifest_sha256"]
                assert v["source_manifest_sha256"] == untreated[dataset]["manifest_sha256"]
                assert s["protocol_hash"] == untreated[dataset]["protocol_hash"]
                kept_rows = load_candidate_manifest(manifest_path)
                removed = set(v["removed_sample_ids"])
                assert {r["sample_id"] for r in kept_rows} == set(truth) - removed
                assert all(r == source_by_id[r["sample_id"]] for r in kept_rows)
            row = {"dataset": dataset, "strategy": strategy,
                   "retained": len(kept_rows), "removed": len(removed),
                   "poison_removed": len(removed & original_poison),
                   "clean_removed": len(removed - original_poison),
                   "poison_remaining": len(original_poison - removed),
                   "retained_candidate_class_counts": dict(Counter(r["assigned_label"] for r in kept_rows)),
                   "test_accuracy": s["test"]["accuracy"], "test_macro_f1": s["test"]["macro_f1"],
                   "targeted_error_rate": s["test"]["targeted_0_to_1_rate"],
                   "accuracy_delta_vs_untreated_pp": round(100*(s["test"]["accuracy"]-untreated[dataset]["test"]["accuracy"]),4)}
            rows.append(row)
    report = {"policy": plan["policy"], "selection_plan_sha256": sha(plan_path), "rows": rows,
              "limitations": ["One training seed and one fixed removal seed; no confidence intervals.",
                "Thresholds unchanged; no test-driven retuning or corrected labels.",
                "Fixed epochs, not equal optimizer updates; random control matches retained count but not class distribution.",
                "Results apply to this controlled label-flip setup, not all poisoning attacks."]}
    (root / "comparison.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    lines = ["# STL-10 防御后重训练与随机删除对照", "",
             "策略：仅保留 ALLOW；REVIEW/QUARANTINE 暂不进入训练，不纠正标签。检测器和阈值保持固定。",
             "8个新模型沿用基线的 seed=2026、20 epochs、ResNet18 预训练权重及验证集选模规则。",
             "随机对照删除相同数量图片；另用干净组衡量误隔离代价。", "",
             "| 条件 | 策略 | 保留图片 | 测试准确率 | Macro-F1 | 飞机→鸟错误率 | 比未处理准确率变化 |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['dataset']} | {r['strategy']} | {r['retained']} | {r['test_accuracy']:.2%} | {r['test_macro_f1']:.4f} | {r['targeted_error_rate']:.3%} | {r['accuracy_delta_vs_untreated_pp']:+.2f} pp |")
    lines += ["", "## 隔离代价（选择和训练冻结后，才读取真值评分）", "",
              "| 条件 | 策略 | 移除投毒样本 | 误移除正常样本 | 剩余投毒样本 |",
              "|---|---|---:|---:|---:|"]
    for r in rows:
        if r["strategy"] != "untreated":
            lines.append(f"| {r['dataset']} | {r['strategy']} | {r['poison_removed']} | {r['clean_removed']} | {r['poison_remaining']} |")
    lines += ["", "单种子结果不能替代多次重复。随机对照匹配总删除数量，未匹配类别分布。固定轮数下删除样本会减少优化步数。",
              "检测结果已在先前实验中观察过，本轮是固定策略的下游验证，不能描述成完全未见攻击上的最终盲测。",
              "模型文件、输入清单、训练协议和逐样本测试指标均已核验。", "", "![防御对照](defense_comparison.png)", ""]
    (root / "defense_report_ZH.md").write_text("\n".join(lines),encoding="utf-8")
    fig, axes = plt.subplots(1,2,figsize=(12,4.5))
    x=np.arange(4); width=.25
    for i,strategy in enumerate(("untreated","random","semantic")):
        subset=[next(r for r in rows if r["dataset"]==d and r["strategy"]==strategy) for d in DATASETS]
        axes[0].bar(x+(i-1)*width,[100*r["test_accuracy"] for r in subset],width,label=strategy)
        axes[1].bar(x+(i-1)*width,[100*r["targeted_error_rate"] for r in subset],width,label=strategy)
    for ax in axes:
        ax.set_xticks(x,["Clean","5% flip","10% flip","Targeted"])
        ax.legend(fontsize=8);ax.grid(axis="y",alpha=.2)
    axes[0].set(title="Test accuracy",ylabel="Percent",ylim=(0,100))
    axes[1].set(title="Airplane classified as bird",ylabel="Percent")
    fig.suptitle("STL-10: fixed defense vs equal-count random removal (seed 2026)")
    fig.tight_layout();fig.savefig(root / "defense_comparison.png",dpi=180);plt.close(fig)
    print(json.dumps(rows,indent=2))
    print("All 12 models and recomputed metrics verified; defense report saved.")


if __name__ == "__main__":
    main()
