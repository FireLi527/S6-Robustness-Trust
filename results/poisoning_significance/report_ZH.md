# 下游分类结果的配对显著性检验

只读取已冻结的逐样本测试预测，不重新训练、不读取隐藏投毒真值。准确率差值为同一种子内 A − B（百分点），
95% 置信区间来自对测试图片的 10,000 次配对 bootstrap；p 值为精确 McNemar 检验，p_holm 为每个数据集主比较族内的 Holm 校正。
定向组另在源类别图片上检验 0→1 错误率（负值表示 A 更好）。

置信区间只反映测试集抽样，不反映重新划分、重新投毒；实蝇为单训练种子，也不反映训练随机性。

## STL-10（测试 8000 张）

### 三种子平均差值

| 条件 | 比较 | 准确率差值 | 95% CI | 0→1 错误率差值 | 95% CI |
|---|---|---:|---|---:|---|
| clean_subset | semantic_minus_untreated | -0.47 | [-0.754, -0.192] | — | — |
| clean_subset | semantic_minus_random | -0.00 | [-0.283, 0.283] | — | — |
| label_flip_05 | semantic_minus_untreated | +0.57 | [0.196, 0.942] | — | — |
| label_flip_05 | semantic_minus_random | +0.98 | [0.596, 1.363] | — | — |
| label_flip_10 | semantic_minus_untreated | +3.23 | [2.821, 3.646] | — | — |
| label_flip_10 | semantic_minus_random | +3.80 | [3.383, 4.246] | — | — |
| targeted_0_to_1 | semantic_minus_untreated | +1.33 | [0.996, 1.667] | -10.25 | [-11.917, -8.667] |
| targeted_0_to_1 | semantic_minus_random | +1.07 | [0.742, 1.404] | -9.17 | [-10.792, -7.667] |

### 逐种子比较

| 条件 | 种子 | 比较 | 准确率差值 | 95% CI | 不一致对 A/B | p | p_holm |
|---|---:|---|---:|---|---|---:|---:|
| clean_subset | 2026 | semantic_minus_untreated | -0.49 | [-0.963, -0.013] | 167/206 | 0.049 | 0.354 |
| clean_subset | 2027 | semantic_minus_untreated | -0.21 | [-0.688, 0.25] | 173/190 | 0.401 | 1.000 |
| clean_subset | 2028 | semantic_minus_untreated | -0.72 | [-1.225, -0.213] | 189/247 | 0.006 | 0.056 |
| clean_subset | 2026 | semantic_minus_random | +0.11 | [-0.388, 0.613] | 209/200 | 0.692 | 1.000 |
| clean_subset | 2027 | semantic_minus_random | +0.41 | [-0.088, 0.912] | 219/186 | 0.112 | 0.559 |
| clean_subset | 2028 | semantic_minus_random | -0.53 | [-1.025, -0.037] | 187/229 | 0.044 | 0.354 |
| label_flip_05 | 2026 | semantic_minus_untreated | +0.33 | [-0.25, 0.9] | 295/269 | 0.292 | 1.000 |
| label_flip_05 | 2027 | semantic_minus_untreated | +0.82 | [0.263, 1.375] | 287/221 | 0.004 | 0.039 |
| label_flip_05 | 2028 | semantic_minus_untreated | +0.56 | [-0.062, 1.188] | 358/313 | 0.089 | 0.536 |
| label_flip_05 | 2026 | semantic_minus_random | +0.90 | [0.325, 1.5] | 316/244 | 0.003 | 0.029 |
| label_flip_05 | 2027 | semantic_minus_random | +1.81 | [1.213, 2.388] | 354/209 | <0.001 | <0.001 |
| label_flip_05 | 2028 | semantic_minus_random | +0.24 | [-0.388, 0.875] | 339/320 | 0.483 | 1.000 |
| label_flip_10 | 2026 | semantic_minus_untreated | +3.90 | [3.275, 4.525] | 480/168 | <0.001 | <0.001 |
| label_flip_10 | 2027 | semantic_minus_untreated | +3.12 | [2.513, 3.737] | 441/191 | <0.001 | <0.001 |
| label_flip_10 | 2028 | semantic_minus_untreated | +2.67 | [2.05, 3.312] | 448/234 | <0.001 | <0.001 |
| label_flip_10 | 2026 | semantic_minus_random | +3.96 | [3.338, 4.612] | 495/178 | <0.001 | <0.001 |
| label_flip_10 | 2027 | semantic_minus_random | +4.16 | [3.537, 4.8] | 508/175 | <0.001 | <0.001 |
| label_flip_10 | 2028 | semantic_minus_random | +3.29 | [2.637, 3.925] | 470/207 | <0.001 | <0.001 |
| targeted_0_to_1 | 2026 | semantic_minus_untreated | +1.05 | [0.525, 1.587] | 287/203 | <0.001 | 0.002 |
| targeted_0_to_1 | 2027 | semantic_minus_untreated | +1.70 | [1.163, 2.237] | 305/169 | <0.001 | <0.001 |
| targeted_0_to_1 | 2028 | semantic_minus_untreated | +1.25 | [0.725, 1.775] | 276/176 | <0.001 | <0.001 |
| targeted_0_to_1 | 2026 | semantic_minus_random | +1.12 | [0.6, 1.663] | 289/199 | <0.001 | <0.001 |
| targeted_0_to_1 | 2027 | semantic_minus_random | +1.02 | [0.513, 1.562] | 264/182 | <0.001 | 0.002 |
| targeted_0_to_1 | 2028 | semantic_minus_random | +1.06 | [0.562, 1.575] | 258/173 | <0.001 | <0.001 |

### 定向组源类别 0→1 错误率

| 种子 | 比较 | 源类图片 | A 错误率 | B 错误率 | 差值 | 95% CI | p | p_holm |
|---:|---|---:|---:|---:|---:|---|---:|---:|
| 2026 | semantic_minus_untreated | 800 | 0.12 | 10.00 | -9.88 | [-12.0, -7.875] | <0.001 | <0.001 |
| 2027 | semantic_minus_untreated | 800 | 0.25 | 14.50 | -14.25 | [-16.625, -11.875] | <0.001 | <0.001 |
| 2028 | semantic_minus_untreated | 800 | 0.25 | 6.88 | -6.62 | [-8.375, -5.0] | <0.001 | <0.001 |
| 2026 | semantic_minus_random | 800 | 0.12 | 8.88 | -8.75 | [-10.75, -6.875] | <0.001 | <0.001 |
| 2027 | semantic_minus_random | 800 | 0.25 | 9.75 | -9.50 | [-11.625, -7.5] | <0.001 | <0.001 |
| 2028 | semantic_minus_random | 800 | 0.25 | 9.50 | -9.25 | [-11.375, -7.375] | <0.001 | <0.001 |

## 实蝇 grouped_defense_v1（测试 1321 张）

### 逐种子比较

| 条件 | 种子 | 比较 | 准确率差值 | 95% CI | 不一致对 A/B | p | p_holm |
|---|---:|---|---:|---|---|---:|---:|
| clean_subset | 2026 | semantic_minus_untreated | +0.23 | [-0.151, 0.606] | 5/2 | 0.453 | 1.000 |
| clean_subset | 2026 | semantic_minus_random | +0.68 | [0.151, 1.287] | 12/3 | 0.035 | 0.211 |
| label_flip_05 | 2026 | semantic_minus_untreated | +0.68 | [0.0, 1.363] | 16/7 | 0.093 | 0.373 |
| label_flip_05 | 2026 | semantic_minus_random | +0.91 | [0.151, 1.665] | 19/7 | 0.029 | 0.203 |
| label_flip_10 | 2026 | semantic_minus_untreated | +2.19 | [1.287, 3.179] | 35/6 | <0.001 | <0.001 |
| label_flip_10 | 2026 | semantic_minus_random | +0.45 | [-0.454, 1.363] | 22/16 | 0.418 | 1.000 |
| targeted_0_to_1 | 2026 | semantic_minus_untreated | -0.83 | [-1.59, -0.076] | 7/18 | 0.043 | 0.216 |
| targeted_0_to_1 | 2026 | semantic_minus_random | -0.30 | [-1.136, 0.454] | 12/16 | 0.572 | 1.000 |

### 定向组源类别 0→1 错误率

| 种子 | 比较 | 源类图片 | A 错误率 | B 错误率 | 差值 | 95% CI | p | p_holm |
|---:|---|---:|---:|---:|---:|---|---:|---:|
| 2026 | semantic_minus_untreated | 172 | 1.16 | 3.49 | -2.33 | [-5.233, 0.0] | 0.219 | 0.250 |
| 2026 | semantic_minus_random | 172 | 1.16 | 3.49 | -2.33 | [-4.651, -0.581] | 0.125 | 0.250 |

### 探索性比较（D2.8 风险加权训练，不计入 Holm 族）

D2.8 的 8 组训练已于 2026-09-28 全部完成，但 floor=0.25 先于 floor=0.50 出结果，这两个比较族在看到部分结果之后才确定要不要继续训练；为避免在看到结果后再决定入选 Holm 主族，两个 floor 都维持为探索性、不做多重比较校正。

| 条件 | 比较 | 准确率差值 | 95% CI | p | 0→1 错误率差值 | 95% CI | p |
|---|---|---:|---|---:|---:|---|---:|
| clean_subset | weighted_25_minus_untreated | +0.15 | [-0.227, 0.606] | 0.727 | — | — | — |
| clean_subset | weighted_25_minus_semantic | -0.08 | [-0.379, 0.227] | 1.000 | — | — | — |
| clean_subset | weighted_50_minus_untreated | +0.38 | [-0.076, 0.833] | 0.180 | — | — | — |
| clean_subset | weighted_50_minus_semantic | +0.15 | [-0.227, 0.606] | 0.727 | — | — | — |
| label_flip_05 | weighted_25_minus_untreated | +0.45 | [-0.227, 1.136] | 0.286 | — | — | — |
| label_flip_05 | weighted_25_minus_semantic | -0.23 | [-0.908, 0.379] | 0.648 | — | — | — |
| label_flip_05 | weighted_50_minus_untreated | -0.53 | [-1.287, 0.227] | 0.230 | — | — | — |
| label_flip_05 | weighted_50_minus_semantic | -1.21 | [-1.97, -0.454] | 0.004 | — | — | — |
| label_flip_10 | weighted_25_minus_untreated | +2.04 | [1.136, 2.952] | <0.001 | — | — | — |
| label_flip_10 | weighted_25_minus_semantic | -0.15 | [-0.757, 0.454] | 0.815 | — | — | — |
| label_flip_10 | weighted_50_minus_untreated | +2.42 | [1.287, 3.558] | <0.001 | — | — | — |
| label_flip_10 | weighted_50_minus_semantic | +0.23 | [-0.53, 1.06] | 0.711 | — | — | — |
| targeted_0_to_1 | weighted_25_minus_untreated | +0.08 | [-0.53, 0.681] | 1.000 | -2.33 | [-5.233, 0.0] | 0.219 |
| targeted_0_to_1 | weighted_25_minus_semantic | +0.91 | [0.227, 1.665] | 0.023 | +0.00 | [-1.744, 1.744] | 1.000 |
| targeted_0_to_1 | weighted_50_minus_untreated | +0.00 | [-0.606, 0.606] | 1.000 | -1.74 | [-4.651, 1.163] | 0.453 |
| targeted_0_to_1 | weighted_50_minus_semantic | +0.83 | [0.076, 1.59] | 0.043 | +0.58 | [-1.163, 2.907] | 1.000 |
