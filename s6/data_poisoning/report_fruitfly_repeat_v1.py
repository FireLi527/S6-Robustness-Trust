"""Summarize the frozen three-seed fruit-fly repeat after every run finishes."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from prepare_fruitfly import DATA, RESULTS, sha

PROTOCOL = DATA / "multiseed_v1/protocol.json"
OUTPUT = RESULTS / "multiseed_v1"
GROUPED = RESULTS / "grouped_defense_v1/model_training"
WEIGHTED = RESULTS / "weighted_v2"


def summary_path(job_key: str, job: dict, seed: int) -> Path:
    manifest_name = Path(job["manifest"]).stem
    if seed == 2026:
        root = WEIGHTED if job["strategy"] == "weighted" else GROUPED
    else:
        root = OUTPUT
    candidates = list((root / manifest_name).glob(f"resnet18_seed{seed}_*/summary.json"))
    if len(candidates) != 1:
        raise FileNotFoundError(f"Expected one completed summary for {job_key} seed={seed}; found {len(candidates)}")
    return candidates[0]


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for job_key, job in protocol["jobs"].items():
        for seed in [protocol["existing_seed"], *protocol["additional_seeds"]]:
            path = summary_path(job_key, job, seed)
            summary = json.loads(path.read_text(encoding="utf-8"))
            if summary.get("status") != "COMPLETE" or summary.get("protocol", {}).get("seed") != seed:
                raise ValueError(f"Incomplete or wrong-seed summary: {path}")
            if summary.get("manifest_sha256") != job["sha256"] or summary.get("test_samples") != 1321:
                raise ValueError(f"Manifest or test split mismatch: {path}")
            if seed != 2026 and summary.get("repeat_protocol_sha256") != sha(PROTOCOL):
                raise ValueError(f"Repeat protocol mismatch: {path}")
            rows.append({
                "scenario": job["scenario"], "strategy": job["strategy"], "job": job_key,
                "seed": seed, "test_accuracy": summary["test"]["accuracy"],
                "macro_f1": summary["test"]["macro_f1"],
                "targeted_error": summary["test"]["targeted_0_to_1_rate"],
            })

    comparisons: list[dict] = []
    for scenario in ("label_flip_10", "targeted_0_to_1"):
        for seed in [2026, 2027, 2028]:
            subset = {r["strategy"]: r for r in rows if r["scenario"] == scenario and r["seed"] == seed}
            for baseline in ("semantic", "untreated"):
                comparisons.append({
                    "scenario": scenario, "seed": seed, "comparison": f"weighted_minus_{baseline}",
                    "accuracy_gain_pp": 100 * (subset["weighted"]["test_accuracy"] - subset[baseline]["test_accuracy"]),
                    "targeted_error_change_pp": 100 * (subset["weighted"]["targeted_error"] - subset[baseline]["targeted_error"]),
                })
    grouped: list[dict] = []
    for scenario in ("label_flip_10", "targeted_0_to_1"):
        for strategy in ("untreated", "semantic", "weighted"):
            values = [r["test_accuracy"] for r in rows if r["scenario"] == scenario and r["strategy"] == strategy]
            grouped.append({
                "scenario": scenario, "strategy": strategy,
                "accuracy_mean": statistics.mean(values), "accuracy_sample_sd": statistics.stdev(values),
            })
    result = {
        "status": "COMPLETE", "protocol_sha256": sha(PROTOCOL), "rows": rows,
        "paired_comparisons": comparisons, "three_seed_summary": grouped,
        "interpretation": "Exploratory: conditions and floors were selected after inspecting seed-2026 test results; same poisoned instances and test images in all three runs.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 五类实蝇多种子重复（探索性）", "",
        "种子 2026/2027/2028；同一投毒实例、同一测试集、相同训练配置。条件和加权下限是在查看种子 2026 结果后选定，因此不能称为预先选定的独立确认实验。", "",
        "| 场景 | 策略 | 测试准确率均值 ± 样本标准差 |", "|---|---|---:|",
    ]
    for item in grouped:
        lines.append(f"| {item['scenario']} | {item['strategy']} | {item['accuracy_mean']:.2%} ± {item['accuracy_sample_sd']:.2%} |")
    lines += ["", "| 场景 | 种子 | 加权相对对照 | 准确率差值（百分点） | 0→1 错误率差值（百分点） |", "|---|---:|---|---:|---:|"]
    for item in comparisons:
        lines.append(f"| {item['scenario']} | {item['seed']} | {item['comparison']} | {item['accuracy_gain_pp']:+.2f} | {item['targeted_error_change_pp']:+.2f} |")
    lines += ["", "这只度量固定划分、固定投毒实例下的训练种子波动。三种子不足以推断跨数据集或跨投毒实例的普遍收益。", ""]
    (OUTPUT / "report_ZH.md").write_text("\n".join(lines), encoding="utf-8")
    print("COMPLETE fruit-fly three-seed report")


if __name__ == "__main__":
    main()
