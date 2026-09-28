# 五类实蝇多种子重复（探索性）

种子 2026/2027/2028；同一投毒实例、同一测试集、相同训练配置。条件和加权下限是在查看种子 2026 结果后选定，因此不能称为预先选定的独立确认实验。

| 场景 | 策略 | 测试准确率均值 ± 样本标准差 |
|---|---|---:|
| label_flip_10 | untreated | 97.45% ± 1.19% |
| label_flip_10 | semantic | 98.28% ± 0.42% |
| label_flip_10 | weighted | 98.11% ± 1.02% |
| targeted_0_to_1 | untreated | 98.54% ± 0.35% |
| targeted_0_to_1 | semantic | 98.69% ± 0.50% |
| targeted_0_to_1 | weighted | 99.22% ± 0.42% |

| 场景 | 种子 | 加权相对对照 | 准确率差值（百分点） | 0→1 错误率差值（百分点） |
|---|---:|---|---:|---:|
| label_flip_10 | 2026 | weighted_minus_semantic | +0.23 | +0.00 |
| label_flip_10 | 2026 | weighted_minus_untreated | +2.42 | +0.00 |
| label_flip_10 | 2027 | weighted_minus_semantic | +0.53 | +0.00 |
| label_flip_10 | 2027 | weighted_minus_untreated | -0.38 | +0.00 |
| label_flip_10 | 2028 | weighted_minus_semantic | -1.29 | +0.00 |
| label_flip_10 | 2028 | weighted_minus_untreated | -0.08 | -0.58 |
| targeted_0_to_1 | 2026 | weighted_minus_semantic | +0.91 | +0.00 |
| targeted_0_to_1 | 2026 | weighted_minus_untreated | +0.08 | -2.33 |
| targeted_0_to_1 | 2027 | weighted_minus_semantic | +0.68 | -2.91 |
| targeted_0_to_1 | 2027 | weighted_minus_untreated | +1.36 | -0.58 |
| targeted_0_to_1 | 2028 | weighted_minus_semantic | +0.00 | +0.00 |
| targeted_0_to_1 | 2028 | weighted_minus_untreated | +0.61 | -5.81 |

这只度量固定划分、固定投毒实例下的训练种子波动。三种子不足以推断跨数据集或跨投毒实例的普遍收益。
