# 实蝇风险加权训练（D2.8）汇总报告

8 组训练全部完成（floor ∈ {0.25, 0.50} × 4 条件），协议已冻结（`data/fruitfly_poisoning/weighted_v2/protocol.json`），未使用隐藏真值或测试指标来选 floor。
未处理/等量随机删除/语义标本分组隔离三列复用 D2.7 `grouped_defense_v1/comparison.json` 中已核验的冻结数字，本脚本不重新计算。

| 条件 | 策略 | 训练数 | 测试准确率 | Macro-F1 | correcta→zonata 错误率 | 相对未处理准确率变化 |
|---|---|---:|---:|---:|---:|---:|
| clean_subset | untreated | 6531 | 99.24% | 0.9914 | 0.00% | +0.00 pp |
| clean_subset | random | 6466 | 98.79% | 0.9860 | 0.00% | -0.45 pp |
| clean_subset | semantic | 6466 | 99.47% | 0.9941 | 0.00% | +0.23 pp |
| clean_subset | weighted_25 | 6531 | 99.39% | 0.9930 | 0.00% | +0.15 pp |
| clean_subset | weighted_50 | 6531 | 99.62% | 0.9954 | 0.00% | +0.38 pp |
| label_flip_05 | untreated | 6531 | 98.33% | 0.9807 | 0.00% | +0.00 pp |
| label_flip_05 | random | 6218 | 98.11% | 0.9777 | 0.00% | -0.23 pp |
| label_flip_05 | semantic | 6218 | 99.02% | 0.9894 | 0.00% | +0.68 pp |
| label_flip_05 | weighted_25 | 6531 | 98.79% | 0.9868 | 0.00% | +0.45 pp |
| label_flip_05 | weighted_50 | 6531 | 97.80% | 0.9762 | 0.00% | -0.53 pp |
| label_flip_10 | untreated | 6531 | 96.52% | 0.9625 | 0.00% | +0.00 pp |
| label_flip_10 | random | 6015 | 98.26% | 0.9798 | 0.00% | +1.74 pp |
| label_flip_10 | semantic | 6015 | 98.71% | 0.9858 | 0.00% | +2.20 pp |
| label_flip_10 | weighted_25 | 6531 | 98.56% | 0.9835 | 0.00% | +2.04 pp |
| label_flip_10 | weighted_50 | 6531 | 98.94% | 0.9871 | 0.00% | +2.42 pp |
| targeted_0_to_1 | untreated | 6531 | 98.94% | 0.9874 | 3.49% | +0.00 pp |
| targeted_0_to_1 | random | 6385 | 98.41% | 0.9810 | 3.49% | -0.53 pp |
| targeted_0_to_1 | semantic | 6385 | 98.11% | 0.9769 | 1.16% | -0.83 pp |
| targeted_0_to_1 | weighted_25 | 6531 | 99.02% | 0.9888 | 1.16% | +0.08 pp |
| targeted_0_to_1 | weighted_50 | 6531 | 98.94% | 0.9875 | 1.74% | +0.00 pp |

## 读法

- `weighted_25`/`weighted_50` 只降低可疑样本的监督损失权重（`weight = max(floor, 1 − risk)`），不删除任何样本；`semantic` 是 D2.7 的标本分组隔离（判为高风险即从参考集整体剔除）。两者用同一批 D2.7 冻结风险分数，是同一份风险信号的两种不同下游用法，不是互相替代的方法。
- floor 越小，降权越激进（风险接近 1 的样本权重可降到 0.25）；floor=0.50 是更保守的降权。
- 本表只是描述性汇总；配对显著性检验（含 Holm 校正边界、95% 置信区间）见 `results/poisoning_significance/report_ZH.md` 的"D2.8"探索性比较部分。

## 解释边界

单训练种子、固定一组投毒实例，不能宣称普遍有效。D2.8 的两个比较（weighted vs untreated、weighted vs semantic）在看到 floor=0.25 的结果之后才决定继续训练 floor=0.50 并入报告，因此始终标记为探索性比较，不并入 D2.7 的 Holm 校正主比较族。
