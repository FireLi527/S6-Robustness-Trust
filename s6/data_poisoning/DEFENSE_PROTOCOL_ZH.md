# STL-10 固定策略防御实验

## 预先固定的实验设计

- 沿用语义检测器 v0.5.0 和冻结的逐样本判定，不更改阈值或根据模型测试结果选择样本。
- 仅 ALLOW 进入训练。REVIEW 和 QUARANTINE 暂缓摄取，保留原图片与原清单，不纠正标签。
- 每种数据条件增加两个模型：检测器筛选后的模型、随机删除相同数量样本的模型。
- 对干净清单也运行这两个策略，测量误报造成的训练代价。
- 8 个新模型均使用原四组训练的相同设置：seed=2026，20 epochs，batch size=32，ImageNet 预训练 ResNet18，AdamW，余弦学习率与 AMP。
- 验证集与测试集不改变，按验证 Macro-F1 选模。原四组已完成训练直接作为未防御对照，不覆盖旧结果。

| 数据条件 | 检测器隔离数量 | 防御/随机组各自保留数量 |
|---|---:|---:|
| 干净 | 60 | 3940 |
| 5% 翻转 | 253 | 3747 |
| 10% 翻转 | 446 | 3554 |
| 定向翻转 | 137 | 3863 |

## 防止使用隐藏答案

`prepare_stl10_defense.py` 只读取候选清单和冻结的检测判定。它不导入或读取隐藏真值。选择清单和移除 ID 在训练前写入 `data/stl10_poisoning/defense/selection_plan.json` 并绑定哈希。

`train_stl10_defense.py` 使用原训练器、独立候选清单目录和独立模型输出目录。它核对原训练器与评估划分未变。

`report_stl10_defense.py` 仅在全部模型完成后读取隐藏真值，评分移除投毒数、误移除正常数和剩余投毒数，不反馈至选择步骤。

## 解释边界

这是单训练种子和单随机删除种子的实验。随机对照匹配总删除数，不匹配类别分布。固定轮数下，不同数据量意味着不同优化步数；因此应同时比较等量随机组。

检测器的攻击指标已经在此前查看过，本轮不宣称未见攻击最终盲测；它验证的是预先固定策略的下游效果。生产中的 REVIEW 通常进入人工复核，本轮模拟的是复核完成前暂不用于训练，没有假设人工一定能够纠正全部标签。

运行顺序（准备可用 Windows Python，训练/报告使用现有 WSL GPU 环境）：

```text
python s6/data_poisoning/prepare_stl10_defense.py
python s6/data_poisoning/train_stl10_defense.py
python s6/data_poisoning/report_stl10_defense.py
```

结果写入 `results/stl10_poisoning/defense_training/`，模型写入 `~/s6-training-artifacts/stl10/defense/`。训练脚本可恢复已完成且哈希一致的实验，不把未完成实验当作成功。

## 多训练种子重复（2026-09-19 扩展）

固定训练种子为 2026、2027、2028。复用 2026 已完成的 12 个模型，新增 24 个模型；每个种子覆盖四种数据条件和未处理、等量随机删除、语义隔离三种策略。

只改变训练随机性（分类头初始化、批次顺序、数据增强等）。数据划分、投毒位置、随机删除清单、语义判定和训练超参数均冻结。随机删除清单继续沿用原 selection_plan，不随训练种子改变。仍采用完整的 1000 张验证图片和 8000 张测试图片，按验证 Macro-F1 选模。

```text
python s6/data_poisoning/train_stl10_multiseed.py --verify-only
python s6/data_poisoning/train_stl10_multiseed.py
python s6/data_poisoning/report_stl10_multiseed.py
```

使用现有 WSL GPU Python。训练入口先验证原有 12 次结果，再冻结 results/stl10_poisoning/multiseed_training/protocol.json。每完成一组，原子更新该目录的 progress.json；再次运行会校验并跳过完成项，未完成项从头训练。全部完成后自动输出 multiseed_report_ZH.md、comparison.json 和 multiseed_comparison.png。新模型位于 ~/s6-training-artifacts/stl10/multiseed/。

报告给出均值、样本标准差（ddof=1）和每个种子的结果；防御增益先在同一种子内配对相减，再汇总。三个训练种子只衡量当前固定数据和固定选择下的训练波动，不能代表重新划分数据或重新投毒的方差，也不据此宣称统计显著或普遍有效。
