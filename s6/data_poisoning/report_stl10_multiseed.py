"""Verify all repetitions and report sample SD and within-seed paired effects."""
import json
from pathlib import Path
from statistics import mean, stdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from dataset_config import RESULTS_ROOT
from prepare_stl10_defense import DATASETS, sha
from train_stl10_multiseed import OUTPUT, SEEDS, read, require, verify

METRICS = ("accuracy", "macro_f1", "targeted_0_to_1_rate")
STRATEGIES = ("untreated", "random", "semantic")


def statistics(values):
    require(len(values) == len(SEEDS), "Missing repetitions")
    return {"mean": mean(values), "sample_sd": stdev(values), "values_by_seed": dict(zip(SEEDS, values))}


def main():
    progress = read(OUTPUT / "progress.json")
    protocol = read(OUTPUT / "protocol.json")
    require(progress["protocol_sha256"] == sha(OUTPUT / "protocol.json"), "Protocol changed")
    require(progress["completed_runs"] == progress["expected_runs"] == 36, "Incomplete experiment")
    originals = {s["dataset"]: s for s in
                 read(RESULTS_ROOT / "model_training" / "comparison_summary.json")["summaries"] +
                 read(RESULTS_ROOT / "defense_training" / "defense_results.json")["summaries"]}
    runs = {}
    for s in progress["summaries"]:
        key = (s["protocol"]["seed"], s["dataset"])
        require(key not in runs, "Duplicate seed/condition")
        require(key[0] in SEEDS and key[1] in originals, "Unexpected seed/condition")
        require(s["manifest_sha256"] == protocol["manifest_sha256"][key[1]], "Manifest differs from protocol")
        verify(s, originals[key[1]], key[0])
        runs[key] = s
    require(set(runs) == {(seed, name) for seed in SEEDS for name in originals}, "Missing seed/condition")
    rows, paired = [], []
    for dataset in DATASETS:
        for strategy in STRATEGIES:
            name = dataset if strategy == "untreated" else f"{dataset}__{strategy}"
            rows.append({"dataset": dataset, "strategy": strategy,
                         **{metric: statistics([runs[seed, name]["test"][metric] for seed in SEEDS])
                            for metric in METRICS}})
        for reference in ("untreated", "random"):
            reference_name = dataset if reference == "untreated" else f"{dataset}__random"
            paired.append({"dataset": dataset, "comparison": f"semantic_minus_{reference}",
                           **{metric: statistics([100 * (runs[seed, f"{dataset}__semantic"]["test"][metric] -
                                                               runs[seed, reference_name]["test"][metric]) for seed in SEEDS])
                              for metric in METRICS}})
    result = {"seeds": list(SEEDS), "n": 3, "sd_ddof": 1, "rows": rows, "paired_differences_pp": paired,
              "scope": protocol["scope"], "protocol_sha256": sha(OUTPUT / "protocol.json")}
    (OUTPUT / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# STL-10 多训练种子重复", "",
             "训练种子 2026、2027、2028；4 种数据条件 × 3 种处理策略 × 3 个种子 = 36 个模型。",
             "2026 的 12 个模型复用既有结果，新增 24 个模型。全部模型校验输入哈希、训练协议、检查点与逐样本测试指标。",
             "固定数据划分、投毒样本、检测器、阈值、语义隔离与随机删除清单，只改变训练随机性。每次 20 epochs，按验证集 Macro-F1 选模。",
             "均值 ± 样本标准差（n=3，ddof=1）；不是置信区间。", "",
             "| 条件 | 策略 | 测试准确率（%） | Macro-F1 | 飞机→鸟错误率（%） |",
             "|---|---|---:|---:|---:|"]
    for row in rows:
        a, f, t = (row[m] for m in METRICS)
        lines.append(f"| {row['dataset']} | {row['strategy']} | {100*a['mean']:.2f} ± {100*a['sample_sd']:.2f} | {f['mean']:.4f} ± {f['sample_sd']:.4f} | {100*t['mean']:.3f} ± {100*t['sample_sd']:.3f} |")
    lines += ["", "## 同一种子配对差值", "", "先在每个种子内相减，再计算均值与标准差；全部单位为百分点（pp）。准确率差值正数表示提升，飞机→鸟错误率差值负数表示改善。", "",
              "| 条件 | 比较 | 准确率差值均值 ± SD | 各种子准确率差值（2026 / 2027 / 2028） | 飞机→鸟错误率差值均值 ± SD |",
              "|---|---|---:|---|---:|"]
    for row in paired:
        a, t = row['accuracy'], row['targeted_0_to_1_rate']
        values = " / ".join(f"{v:+.3f}" for v in a['values_by_seed'].values())
        lines.append(f"| {row['dataset']} | {row['comparison']} | {a['mean']:+.3f} ± {a['sample_sd']:.3f} | {values} | {t['mean']:+.3f} ± {t['sample_sd']:.3f} |")
    lines += ["", "## 结论边界", "",
              "本实验衡量固定数据和固定防御选择下的训练随机性，不衡量换数据划分、重新投毒、重新随机删除带来的不确定性。",
              "3 个种子不足以支持普遍有效或统计显著的强结论；需要结合每个种子的配对差值判断方向是否一致。",
              "随机对照仅匹配总删除数，未匹配类别分布；固定轮数下不同训练集大小意味着不同优化步数。",
              "干净组用于衡量误隔离代价。原有选择与阈值在本次重复前已固定，但本研究已观察过先前攻击结果。",
              "", "![均值、标准差与各种子结果](multiseed_comparison.png)", ""]
    (OUTPUT / "multiseed_report_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    x = np.arange(len(DATASETS)); width = .24
    for i, strategy in enumerate(STRATEGIES):
        subset = [next(r for r in rows if r['dataset'] == d and r['strategy'] == strategy) for d in DATASETS]
        for ax, metric in zip(axes, ("accuracy", "targeted_0_to_1_rate")):
            positions = x + (i - 1) * width
            ax.bar(positions, [100*r[metric]['mean'] for r in subset], width,
                   yerr=[100*r[metric]['sample_sd'] for r in subset], capsize=3, label=strategy, alpha=.75)
            for pos, row in zip(positions, subset):
                ax.scatter(pos + np.array([-.04, 0, .04]), [100*v for v in row[metric]['values_by_seed'].values()], s=13, color='black', zorder=4)
    for ax in axes:
        ax.set_xticks(x, ["Clean", "5% flip", "10% flip", "Targeted"])
        ax.grid(axis='y', alpha=.2); ax.legend(fontsize=8); ax.set_ylabel('Percent')
    axes[0].set(title='Test accuracy', ylim=(0, 100))
    axes[1].set_title('Airplane classified as bird')
    fig.suptitle('STL-10: 3 training seeds; bars = mean, error bars = sample SD, dots = runs')
    fig.tight_layout(); fig.savefig(OUTPUT / 'multiseed_comparison.png', dpi=180); plt.close(fig)
    print(json.dumps(result, indent=2), flush=True)
    print("Verified all 36 models; multiseed report complete.", flush=True)


if __name__ == '__main__':
    main()
