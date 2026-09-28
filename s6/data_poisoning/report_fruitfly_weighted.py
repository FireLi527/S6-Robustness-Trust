"""Verify and report the 8 completed fruit-fly risk-weighted (D2.8) training runs.

Reads only frozen `summary.json`/manifest hashes (no retraining, no hidden ground
truth). Reuses the already-verified D2.7 `grouped_defense_v1/comparison.json` rows
for the untreated/random/semantic baselines so this report never recomputes or
second-guesses those frozen numbers.
"""
import csv
import json
from pathlib import Path

from prepare_fruitfly import DATA, RESULTS, sha, write_json

MANIFESTS = DATA / "weighted_v2"
OUT = RESULTS / "weighted_v2"
CONDITIONS = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")
FLOORS = ("25", "50")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_run(condition, floor):
    name = f"{condition}__weighted_{floor}"
    directory = OUT / name
    candidates = [p for p in directory.iterdir() if p.is_dir() and p.name.startswith("resnet18_")]
    require(len(candidates) == 1, f"Expected exactly one run dir for {name}")
    summary = read(candidates[0] / "summary.json")
    require(summary["dataset"] == name, f"Dataset name mismatch in {name}")
    require(summary["status"] == "COMPLETE", f"Run not complete: {name}")
    return name, summary, candidates[0]


def main():
    protocol = read(MANIFESTS / "protocol.json")
    require(protocol["status"] == "FROZEN", "weighted_v2 protocol not frozen")
    require(protocol["hidden_truth_used"] is False and protocol["test_metrics_used"] is False,
            "Protocol claims hidden truth or test metrics were used")

    runs = {}
    run_dirs = {}
    for condition in CONDITIONS:
        for floor in FLOORS:
            name, summary, run_dir = load_run(condition, floor)
            run_dirs[name] = run_dir
            variant = protocol["variants"][name]
            require(summary["weighted_manifest_sha256"] == variant["manifest_sha256"] == sha(MANIFESTS / f"{name}.csv"),
                    f"Manifest hash mismatch for {name}")
            require(summary["weighted_protocol_sha256"] == sha(MANIFESTS / "protocol.json"),
                    f"Protocol hash mismatch for {name}")
            require(summary["sample_weight_floor"] == floor, f"Floor mismatch for {name}")
            require(summary["training_samples"] == variant["samples"], f"Training sample count mismatch for {name}")
            runs[name] = summary

    base = runs["clean_subset__weighted_25"]
    for name, summary in runs.items():
        require(summary["trainer_sha256"] == base["trainer_sha256"], f"Trainer changed for {name}")
        require({k: v for k, v in summary["protocol"].items() if k != "dataset"}
                == {k: v for k, v in base["protocol"].items() if k != "dataset"},
                f"Hyperparameters changed for {name}")
        require(summary["validation_split_sha256"] == base["validation_split_sha256"], f"Validation split changed for {name}")
        require(summary["test_split_sha256"] == base["test_split_sha256"], f"Test split changed for {name}")
        history = csv_rows(run_dirs[name] / "history.csv")
        require(len(history) == 20, f"Incomplete training history for {name}")

    baseline = {(r["dataset"], r["strategy"]): r for r in read(RESULTS / "grouped_defense_v1" / "comparison.json")["rows"]}

    rows = []
    for condition in CONDITIONS:
        untreated = baseline[(condition, "untreated")]
        for strategy in ("untreated", "random", "semantic"):
            r = baseline[(condition, strategy)]
            rows.append(dict(dataset=condition, strategy=strategy, training_samples=r["training_samples"],
                              test_accuracy=r["test_accuracy"], macro_f1=r["macro_f1"],
                              targeted_error=r["targeted_error"], accuracy_gain_pp=r["accuracy_gain_pp"]))
        for floor in FLOORS:
            name = f"{condition}__weighted_{floor}"
            s = runs[name]
            rows.append(dict(dataset=condition, strategy=f"weighted_{floor}", training_samples=s["training_samples"],
                              test_accuracy=s["test"]["accuracy"], macro_f1=s["test"]["macro_f1"],
                              targeted_error=s["test"]["targeted_0_to_1_rate"],
                              accuracy_gain_pp=100 * (s["test"]["accuracy"] - untreated["test_accuracy"])))

    write_json(OUT / "weighted_comparison.json",
               dict(status="VERIFIED", seed=2026, protocol_sha256=sha(MANIFESTS / "protocol.json"), rows=rows))

    lines = [
        "# 实蝇风险加权训练（D2.8）汇总报告", "",
        "8 组训练全部完成（floor ∈ {0.25, 0.50} × 4 条件），协议已冻结"
        "（`data/fruitfly_poisoning/weighted_v2/protocol.json`），未使用隐藏真值或测试指标来选 floor。",
        "未处理/等量随机删除/语义标本分组隔离三列复用 D2.7 `grouped_defense_v1/comparison.json` 中已核验的冻结数字，本脚本不重新计算。",
        "",
        "| 条件 | 策略 | 训练数 | 测试准确率 | Macro-F1 | correcta→zonata 错误率 | 相对未处理准确率变化 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['dataset']} | {r['strategy']} | {r['training_samples']} | {r['test_accuracy']:.2%} | "
                      f"{r['macro_f1']:.4f} | {r['targeted_error']:.2%} | {r['accuracy_gain_pp']:+.2f} pp |")

    lines += ["", "## 读法", "",
              "- `weighted_25`/`weighted_50` 只降低可疑样本的监督损失权重（`weight = max(floor, 1 − risk)`），不删除任何样本；"
              "`semantic` 是 D2.7 的标本分组隔离（判为高风险即从参考集整体剔除）。两者用同一批 D2.7 冻结风险分数，是同一份风险信号的两种不同下游用法，"
              "不是互相替代的方法。",
              "- floor 越小，降权越激进（风险接近 1 的样本权重可降到 0.25）；floor=0.50 是更保守的降权。",
              "- 本表只是描述性汇总；配对显著性检验（含 Holm 校正边界、95% 置信区间）见 "
              "`results/poisoning_significance/report_ZH.md` 的\"D2.8\"探索性比较部分。",
              "", "## 解释边界", "",
              "单训练种子、固定一组投毒实例，不能宣称普遍有效。D2.8 的两个比较（weighted vs untreated、weighted vs semantic）"
              "在看到 floor=0.25 的结果之后才决定继续训练 floor=0.50 并入报告，因此始终标记为探索性比较，不并入 D2.7 的 Holm 校正主比较族。",
              ""]
    (OUT / "weighted_report_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print("All 8 weighted_v2 runs verified; report saved.", flush=True)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
