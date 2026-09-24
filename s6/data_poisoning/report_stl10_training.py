"""Validate completed STL-10 runs and export report/learning curves."""
from pathlib import Path
import csv
import hashlib
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dataset_config import RESULTS_ROOT, IMAGE_ROOT


def main():
    root = RESULTS_ROOT / "model_training"
    document = json.loads((root / "comparison_summary.json").read_text())
    summaries = document["summaries"]
    assert len(summaries) == 4
    assert len({s["protocol_hash"] for s in summaries}) == 1
    labels = {"clean_subset": "Clean", "label_flip_05": "5% label flip",
              "label_flip_10": "10% label flip", "targeted_0_to_1": "Targeted airplane to bird"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    lines = ["# STL-10 首轮分类模型训练结果", "",
             "四组使用同一 ResNet18 预训练初始化，seed=2026，20 epochs，batch size=32。",
             "训练/验证/测试为 4000/1000/8000，按验证集 Macro-F1 选模。",
             "以下为下游分类模型指标，与语义投毒检测的检出率不同。", "",
             "| 训练数据 | 测试准确率 | Macro-F1 | 飞机→鸟误分类率 | 最佳轮次 |",
             "|---|---:|---:|---:|---:|"]
    for s in summaries:
        assert s["status"] == "COMPLETE"
        assert (s["training_samples"], s["validation_samples"], s["test_samples"]) == (4000, 1000, 8000)
        assert s["protocol"]["seed"] == 2026 and s["protocol"]["epochs"] == 20
        assert Path(s["checkpoint"]).is_file()
        assert hashlib.sha256(Path(s["manifest"]).read_bytes()).hexdigest() == s["manifest_sha256"]
        for split, field in (("val", "validation_split_sha256"), ("test", "test_split_sha256")):
            assert hashlib.sha256((IMAGE_ROOT / f"{split}.txt").read_bytes()).hexdigest() == s[field]
        run = Path(s["result_dir"])
        with (run / "test_predictions.csv").open(encoding="utf-8-sig") as f:
            predictions = list(csv.DictReader(f))
        assert len(predictions) == 8000
        measured = sum(r["true_label"] == r["predicted_label"] for r in predictions) / 8000
        assert abs(measured - s["test"]["accuracy"]) < 1e-6
        source = [r for r in predictions if r["true_label"] == "0"]
        assert len(source) == 800
        targeted = sum(r["predicted_label"] == "1" for r in source) / len(source)
        assert abs(targeted - s["test"]["targeted_0_to_1_rate"]) < 1e-6
        with (run / "history.csv").open(encoding="utf-8-sig") as f:
            history = list(csv.DictReader(f))
        assert len(history) == 20
        epochs = [int(r["epoch"]) for r in history]
        axes[0].plot(epochs, [float(r["train_loss"]) for r in history], label=labels[s["dataset"]])
        axes[1].plot(epochs, [float(r["val_macro_f1"]) for r in history], label=labels[s["dataset"]])
        t = s["test"]
        lines.append(f"| {s['dataset']} | {t['accuracy']:.2%} | {t['macro_f1']:.4f} | {t['targeted_0_to_1_rate']:.2%} | {s['best_epoch']} |")
    axes[0].set(title="Training loss", xlabel="Epoch", ylabel="Cross entropy")
    axes[1].set(title="Validation Macro-F1", xlabel="Epoch", ylabel="Macro-F1")
    for ax in axes:
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle("STL-10 ResNet18: controlled label poisoning (seed 2026)")
    fig.tight_layout()
    fig.savefig(root / "learning_curves.png", dpi=180)
    plt.close(fig)
    lines += ["", "## 解释边界", "",
              "这是单个训练种子、单组固定投毒清单的首轮对照。不能据此认定投毒比例与损害严格单调。",
              "本轮没有防御后重训练组，尚不能证明隔离可疑数据可以恢复性能。",
              "未来重复训练应保持测试集隔离；多个训练种子只测训练随机性，投毒样本抽样随机性需单独实验。",
              "预训练模型与 STL-10 来源可能存在重叠，不能声称完全从未见过相关图像。", "",
              "已核验四组模型文件、清单哈希、20轮历史和每组8000条测试预测，准确率及定向误分类率与逐样本预测一致。", "",
              "![学习曲线](learning_curves.png)", ""]
    (root / "training_report_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print("Training artifacts and recomputed test metrics: PASS")
    print(json.dumps(document["comparisons_vs_clean"], indent=2))


if __name__ == "__main__":
    main()
