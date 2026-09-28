"""Paired significance tests over frozen downstream test predictions (no retraining).

Reads only each run's `summary.json` and `test_predictions.csv` (official test labels,
not hidden poisoning truth). For every same-seed comparison it reports the accuracy
difference with an exact McNemar test and a paired bootstrap 95% CI over test images;
for targeted conditions it also tests the source-class 0 -> 1 error. STL-10 additionally
gets a seed-averaged difference whose bootstrap reuses the same image indices across the
three seeds. Holm correction is applied within each dataset's primary family.

The CIs capture test-set sampling for these fixed models. They do not capture
re-splitting, re-poisoning, or (for fruit fly) training-seed variance.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
OUTPUT = RESULTS / "poisoning_significance"
CONDITIONS = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")
BOOTSTRAP = 10_000
RNG_SEED = 2026


def _single_run(directory: Path) -> Path:
    runs = [path for path in directory.iterdir() if path.is_dir() and path.name.startswith("resnet18_")]
    if len(runs) != 1:
        raise ValueError(f"Expected exactly one run in {directory}, found {len(runs)}")
    return runs[0]


def load_run(directory: Path) -> dict:
    run = _single_run(directory)
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "COMPLETE":
        raise ValueError(f"Run is not complete: {run}")
    with (run / "test_predictions.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = sorted(csv.DictReader(stream), key=lambda row: row["sample_id"])
    if len(rows) != summary["test_samples"]:
        raise ValueError(f"Prediction count mismatch in {run}")
    return {
        "path": str(run.relative_to(ROOT)).replace("\\", "/"),
        "ids": tuple(row["sample_id"] for row in rows),
        "true": np.array([int(row["true_label"]) for row in rows]),
        "pred": np.array([int(row["predicted_label"]) for row in rows]),
    }


def stl10_runs() -> dict[tuple[int, str, str], dict]:
    base = RESULTS / "stl10_poisoning"
    runs = {}
    for condition in CONDITIONS:
        runs[(2026, condition, "untreated")] = base / "model_training" / condition
        for strategy in ("random", "semantic"):
            runs[(2026, condition, strategy)] = base / "defense_training" / f"{condition}__{strategy}"
        for seed in (2027, 2028):
            root = base / "multiseed_training" / f"seed{seed}"
            runs[(seed, condition, "untreated")] = root / condition
            for strategy in ("random", "semantic"):
                runs[(seed, condition, strategy)] = root / f"{condition}__{strategy}"
    return {key: load_run(path) for key, path in runs.items()}


def fruitfly_runs() -> dict[tuple[int, str, str], dict]:
    base = RESULTS / "fruitfly_poisoning"
    runs = {(2026, "clean_subset", "untreated"): base / "model_training" / "clean_subset"}
    for condition in CONDITIONS:
        if condition != "clean_subset":
            runs[(2026, condition, "untreated")] = base / "grouped_defense_v1" / "model_training" / condition
        for strategy in ("random", "semantic"):
            runs[(2026, condition, strategy)] = base / "grouped_defense_v1" / "model_training" / f"{condition}__{strategy}"
    for condition in CONDITIONS:
        # D2.8 (risk-weighted training) is complete (8/8), but was analysed with only
        # weighted_25 available; both floors stay exploratory rather than being promoted
        # to the Holm-corrected primary family after the fact.
        for floor in ("25", "50"):
            directory = base / "weighted_v2" / f"{condition}__weighted_{floor}"
            if directory.is_dir():
                runs[(2026, condition, f"weighted_{floor}")] = directory
    return {key: load_run(path) for key, path in runs.items()}


def _mcnemar(a_success: np.ndarray, b_success: np.ndarray) -> dict:
    only_a = int((a_success & ~b_success).sum())
    only_b = int((b_success & ~a_success).sum())
    p = binomtest(only_a, only_a + only_b, 0.5).pvalue if only_a + only_b else 1.0
    return {"a_only": only_a, "b_only": only_b, "p_value": float(p)}


def _ci(values: np.ndarray) -> list[float]:
    return [round(float(np.percentile(values, 2.5)), 3), round(float(np.percentile(values, 97.5)), 3)]


def compare(a: dict, b: dict, indices: np.ndarray, targeted: bool) -> dict:
    """Compare run a against run b (a - b), in percentage points."""
    if a["ids"] != b["ids"] or not np.array_equal(a["true"], b["true"]):
        raise ValueError(f"Test sets differ: {a['path']} vs {b['path']}")
    a_ok, b_ok = a["pred"] == a["true"], b["pred"] == b["true"]
    diff = a_ok.astype(float) - b_ok.astype(float)
    result = {
        "a": a["path"],
        "b": b["path"],
        "accuracy_a": round(100 * a_ok.mean(), 3),
        "accuracy_b": round(100 * b_ok.mean(), 3),
        "accuracy_diff_pp": round(100 * diff.mean(), 3),
        "accuracy_diff_ci95_pp": _ci(100 * diff[indices].mean(axis=1)),
        "accuracy_mcnemar": _mcnemar(a_ok, b_ok),
    }
    if targeted:
        source = a["true"] == 0
        a_err, b_err = a["pred"][source] == 1, b["pred"][source] == 1
        err_diff = a_err.astype(float) - b_err.astype(float)
        source_indices = np.random.default_rng(RNG_SEED).integers(0, source.sum(), (BOOTSTRAP, int(source.sum())))
        result.update(
            {
                "source_class_images": int(source.sum()),
                "error_0_to_1_a": round(100 * a_err.mean(), 3),
                "error_0_to_1_b": round(100 * b_err.mean(), 3),
                "error_0_to_1_diff_pp": round(100 * err_diff.mean(), 3),
                "error_0_to_1_diff_ci95_pp": _ci(100 * err_diff[source_indices].mean(axis=1)),
                # Success here means "not misclassified as 1"; b_only counts images a gets wrong.
                "error_0_to_1_mcnemar": _mcnemar(~a_err, ~b_err),
            }
        )
    return result


def holm(entries: list[dict], key: str) -> None:
    ordered = sorted(range(len(entries)), key=lambda index: entries[index][key]["p_value"])
    running = 0.0
    for rank, index in enumerate(ordered):
        adjusted = min(1.0, (len(entries) - rank) * entries[index][key]["p_value"])
        running = max(running, adjusted)
        entries[index][key]["p_holm"] = running


def seed_average(runs: dict, seeds: tuple[int, ...], condition: str, a: str, b: str, n: int) -> dict:
    indices = np.random.default_rng(RNG_SEED).integers(0, n, (BOOTSTRAP, n))
    diffs = []
    for seed in seeds:
        first, second = runs[(seed, condition, a)], runs[(seed, condition, b)]
        diffs.append((first["pred"] == first["true"]).astype(float) - (second["pred"] == second["true"]).astype(float))
    mean_diff = np.mean(diffs, axis=0)
    result = {
        "accuracy_diff_pp": round(100 * mean_diff.mean(), 3),
        "accuracy_diff_ci95_pp": _ci(100 * mean_diff[indices].mean(axis=1)),
    }
    if condition == "targeted_0_to_1":
        source = runs[(seeds[0], condition, a)]["true"] == 0
        errors = [
            (runs[(seed, condition, a)]["pred"][source] == 1).astype(float)
            - (runs[(seed, condition, b)]["pred"][source] == 1).astype(float)
            for seed in seeds
        ]
        mean_err = np.mean(errors, axis=0)
        source_indices = np.random.default_rng(RNG_SEED).integers(0, source.sum(), (BOOTSTRAP, int(source.sum())))
        result["error_0_to_1_diff_pp"] = round(100 * mean_err.mean(), 3)
        result["error_0_to_1_diff_ci95_pp"] = _ci(100 * mean_err[source_indices].mean(axis=1))
    return result


def analyse(runs: dict, seeds: tuple[int, ...], pairs: list[tuple[str, str]], exploratory: list[tuple[str, str]]) -> dict:
    n = len(next(iter(runs.values()))["ids"])
    indices = np.random.default_rng(RNG_SEED).integers(0, n, (BOOTSTRAP, n))
    primary, extra = [], []
    for condition in CONDITIONS:
        for group, family in ((pairs, primary), (exploratory, extra)):
            for a, b in group:
                for seed in seeds:
                    if (seed, condition, a) in runs and (seed, condition, b) in runs:
                        entry = compare(runs[(seed, condition, a)], runs[(seed, condition, b)], indices, condition == "targeted_0_to_1")
                        family.append({"condition": condition, "seed": seed, "comparison": f"{a}_minus_{b}", **entry})
    holm(primary, "accuracy_mcnemar")
    targeted = [entry for entry in primary if "error_0_to_1_mcnemar" in entry]
    holm(targeted, "error_0_to_1_mcnemar")
    averaged = []
    if len(seeds) > 1:
        for condition in CONDITIONS:
            for a, b in pairs:
                averaged.append({"condition": condition, "comparison": f"{a}_minus_{b}", **seed_average(runs, seeds, condition, a, b, n)})
    return {"test_images": n, "primary": primary, "exploratory": extra, "seed_averaged": averaged}


def _fmt_p(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def markdown(results: dict) -> str:
    lines = [
        "# 下游分类结果的配对显著性检验",
        "",
        "只读取已冻结的逐样本测试预测，不重新训练、不读取隐藏投毒真值。准确率差值为同一种子内 A − B（百分点），",
        f"95% 置信区间来自对测试图片的 {BOOTSTRAP:,} 次配对 bootstrap；p 值为精确 McNemar 检验，p_holm 为每个数据集主比较族内的 Holm 校正。",
        "定向组另在源类别图片上检验 0→1 错误率（负值表示 A 更好）。",
        "",
        "置信区间只反映测试集抽样，不反映重新划分、重新投毒；实蝇为单训练种子，也不反映训练随机性。",
    ]
    for name, data in results.items():
        lines += ["", f"## {name}（测试 {data['test_images']} 张）", ""]
        if data["seed_averaged"]:
            lines += [
                "### 三种子平均差值",
                "",
                "| 条件 | 比较 | 准确率差值 | 95% CI | 0→1 错误率差值 | 95% CI |",
                "|---|---|---:|---|---:|---|",
            ]
            for entry in data["seed_averaged"]:
                err = entry.get("error_0_to_1_diff_pp")
                lines.append(
                    f"| {entry['condition']} | {entry['comparison']} | {entry['accuracy_diff_pp']:+.2f} | {entry['accuracy_diff_ci95_pp']} | "
                    + (f"{err:+.2f} | {entry['error_0_to_1_diff_ci95_pp']} |" if err is not None else "— | — |")
                )
            lines.append("")
        lines += [
            "### 逐种子比较",
            "",
            "| 条件 | 种子 | 比较 | 准确率差值 | 95% CI | 不一致对 A/B | p | p_holm |",
            "|---|---:|---|---:|---|---|---:|---:|",
        ]
        for entry in data["primary"]:
            test = entry["accuracy_mcnemar"]
            lines.append(
                f"| {entry['condition']} | {entry['seed']} | {entry['comparison']} | {entry['accuracy_diff_pp']:+.2f} | {entry['accuracy_diff_ci95_pp']} | "
                f"{test['a_only']}/{test['b_only']} | {_fmt_p(test['p_value'])} | {_fmt_p(test['p_holm'])} |"
            )
        targeted = [entry for entry in data["primary"] if "error_0_to_1_mcnemar" in entry]
        if targeted:
            lines += [
                "",
                "### 定向组源类别 0→1 错误率",
                "",
                "| 种子 | 比较 | 源类图片 | A 错误率 | B 错误率 | 差值 | 95% CI | p | p_holm |",
                "|---:|---|---:|---:|---:|---:|---|---:|---:|",
            ]
            for entry in targeted:
                test = entry["error_0_to_1_mcnemar"]
                lines.append(
                    f"| {entry['seed']} | {entry['comparison']} | {entry['source_class_images']} | {entry['error_0_to_1_a']:.2f} | {entry['error_0_to_1_b']:.2f} | "
                    f"{entry['error_0_to_1_diff_pp']:+.2f} | {entry['error_0_to_1_diff_ci95_pp']} | {_fmt_p(test['p_value'])} | {_fmt_p(test['p_holm'])} |"
                )
        if data["exploratory"]:
            lines += [
                "",
                "### 探索性比较（D2.8 风险加权训练，不计入 Holm 族）",
                "",
                "D2.8 的 8 组训练已于 2026-09-28 全部完成，但 floor=0.25 先于 floor=0.50 出结果，"
                "这两个比较族在看到部分结果之后才确定要不要继续训练；为避免在看到结果后再决定入选 Holm 主族，"
                "两个 floor 都维持为探索性、不做多重比较校正。",
                "",
                "| 条件 | 比较 | 准确率差值 | 95% CI | p | 0→1 错误率差值 | 95% CI | p |",
                "|---|---|---:|---|---:|---:|---|---:|",
            ]
            for entry in data["exploratory"]:
                err = entry.get("error_0_to_1_diff_pp")
                lines.append(
                    f"| {entry['condition']} | {entry['comparison']} | {entry['accuracy_diff_pp']:+.2f} | {entry['accuracy_diff_ci95_pp']} | "
                    f"{_fmt_p(entry['accuracy_mcnemar']['p_value'])} | "
                    + (
                        f"{err:+.2f} | {entry['error_0_to_1_diff_ci95_pp']} | {_fmt_p(entry['error_0_to_1_mcnemar']['p_value'])} |"
                        if err is not None
                        else "— | — | — |"
                    )
                )
    return "\n".join(lines) + "\n"


def main() -> None:
    pairs = [("semantic", "untreated"), ("semantic", "random")]
    results = {
        "STL-10": analyse(stl10_runs(), (2026, 2027, 2028), pairs, []),
        "实蝇 grouped_defense_v1": analyse(
            fruitfly_runs(),
            (2026,),
            pairs,
            [
                ("weighted_25", "untreated"),
                ("weighted_25", "semantic"),
                ("weighted_50", "untreated"),
                ("weighted_50", "semantic"),
            ],
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = {"bootstrap_resamples": BOOTSTRAP, "rng_seed": RNG_SEED, "results": results}
    (OUTPUT / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUTPUT / "report_ZH.md").write_text(markdown(results), encoding="utf-8")
    print(OUTPUT / "report_ZH.md")


if __name__ == "__main__":
    main()
