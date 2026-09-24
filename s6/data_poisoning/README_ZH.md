# STL-10 图片标签投毒 Baseline

2026-09-11 起，默认图像 baseline 切换到 STL-10。IP102 原始数据、清单、结果和旧训练脚本保留，旧说明见 [IP102 历史记录](README_IP102_HISTORY_ZH.md)。提示词注入 baseline 不变。

## 数据与实验协议

- 使用全部 10 个类别的带标签数据，图片为 96×96 RGB。
- 官方训练集 5,000 张：按 seed=2026 分层划分为候选训练 4,000 张（每类 400）和验证 1,000 张（每类 100）。
- 官方测试集 8,000 张保持独立。10 万张无标签数据不下载、不参与本次实验。
- 四份候选清单使用相同图片：干净、5% 随机标签翻转（200 张）、10% 翻转（400 张）、类别 0 airplane → 类别 1 bird（源类 20%，80 张，总体 2%）。
- 这是自定义 S6 受控标签投毒协议，不是 STL-10 官方十折分类榜单协议。
- 候选清单只含 sample_id、source_relpath、sha256、assigned_label。隐藏投毒真值单独保存，只在冻结检测输出后评分。

## 下载与运行

在项目根目录 PowerShell 中：

```powershell
& .venv-bipia/Scripts/python.exe -m pip install -r s6/data_poisoning/requirements-data.txt
& .venv-bipia/Scripts/python.exe s6/data_poisoning/download_stl10.py
& .venv-bipia/Scripts/python.exe s6/data_poisoning/prepare_stl10_poisoning.py
& .venv-bipia/Scripts/python.exe s6/data_poisoning/evaluate_manifests.py
& .venv-bipia/Scripts/python.exe s6/data_poisoning/evaluate_semantic.py
& .venv-bipia/Scripts/python.exe s6/data_poisoning/app.py
```

或双击 `start.cmd` 启动前后端（需先下载数据）。地址为 http://127.0.0.1:8766。

官方下载缓慢时，下载脚本使用固定版本的公开 Parquet 镜像，校验 SHA-256，并将像素与标签还原成官方二进制格式，核对 torchvision 记录的四项官方 MD5。任何不一致均报错，不进入实验。

## 当前语义检测器 v0.5.0

使用冻结 CLIP ViT-B/32 的原始 512 维特征，组合 15 近邻标签一致率、五折逻辑回归候选标签置信度和类别中心距离。三项权重仍为 0.4/0.4/0.2，REVIEW/QUARANTINE 阈值沿用 0.62/0.75，不依据新投毒结果调参。

移除了旧版跨折 NCA 特征拼接：独立投影空间的向量不能直接混合计算距离。新流程不读取可信原标签来拟合投影。逻辑回归是检测器的轻量统计模型，与下游 ResNet18 是两回事。

风险分数不是已校准的投毒概率。候选标签会影响参考统计；单类数据没有分类器置信度；重复图片必须先处理，避免同图跨折泄漏。冻结特征来自预训练模型，不能声称其预训练数据与 STL-10/ImageNet 来源无重叠。

离线检测结果同时绑定检测器配置/代码和四份清单哈希，防止修改清单后继续显示旧结果。展示抽样优先选择被改标签的样本，仅用于演示，不代表总体分布。

## 文件与训练

- `external/STL10/`：下载与校验后的上游数据。
- `data/stl10_poisoning/images/`：从官方像素无损导出的 PNG 及训练/验证/测试索引。
- `data/stl10_poisoning/manifests/`：候选清单。
- `data/stl10_poisoning/hidden_ground_truth/`：评分真值。
- `results/stl10_poisoning/`：当前评估结果。
- `train_stl10_models.py`：十分类 ResNet18 训练，默认候选训练集 4,000 张，验证 1,000 张，测试 8,000 张。

现有 WSL GPU 环境：

```bash
cd /mnt/e/研究生/高级计算机项目
/home/anima/.venvs/s6-training/bin/python s6/data_poisoning/evaluate_semantic.py
/home/anima/.venvs/s6-training/bin/python s6/data_poisoning/train_stl10_models.py --all --epochs 20 --batch-size 32 --workers 4 --seed 2026 --pretrained --amp
```

训练产物位于 `~/s6-training-artifacts/stl10/`，不会覆盖 IP102 权重。运行完整训练不属于数据集切换的必要步骤；旧 IP102 准确率不能作为 STL-10 的结果。

测试：在 `s6/data_poisoning/` 下运行 `../../.venv-bipia/Scripts/python.exe -B -m unittest discover -s tests -v`。

数据来源：https://cs.stanford.edu/~acoates/stl10/

## 首轮实测（2026-09-11）

以下为候选训练清单上的标签投毒检测，不是下游分类准确率，也不是未见攻击泛化结论。参数未按本轮结果调优。

| 条件 | 精确率 | 检出率 | 干净样本误报率 |
|---|---:|---:|---:|
| clean_subset | — | — | 1.50% |
| label_flip_05 | 79.05% | 100.00% | 1.39% |
| label_flip_10 | 89.69% | 100.00% | 1.28% |
| targeted_0_to_1 | 57.66% | 98.75% | 1.48% |

17 项回归测试通过；四组真实 HTTP 接口、冻结结果读取、图片返回和越界路径拦截通过。STL-10 四组 ResNet18 已完成 seed=2026、20 epochs 首轮训练；模型、清单哈希和逐样本测试指标均已核验。数据集和投影方法同时变化，因此不能把相对历史 IP102 的改善全部归因于数据集。

## 下游分类模型首轮训练已完成（2026-09-18）

| 候选训练集 | 测试准确率 | Macro-F1 | 飞机→鸟误分类率 |
|---|---:|---:|---:|
| 干净 | 94.44% | 0.9444 | 0.375% |
| 5% 标签翻转 | 92.49% | 0.9248 | 0.500% |
| 10% 标签翻转 | 89.89% | 0.8986 | 1.125% |
| 定向标签翻转 | 93.03% | 0.9303 | 10.000% |

四组采用相同训练协议，以验证集 Macro-F1 选模，再评估独立测试集。定向组只改动80张训练标签，目标误分类率增加9.625个百分点。该初始攻击对照为单种子结果；后续防御实验见下节，多种子重复仍待完成。

完整报告与学习曲线见 [训练报告](../../results/stl10_poisoning/model_training/training_report_ZH.md)。可在WSL使用现有训练环境运行 `s6/data_poisoning/report_stl10_training.py`，重新核验和生成报告。

## 防御后重训练已完成（2026-09-19）

固定策略为仅保留 ALLOW，REVIEW/QUARANTINE 暂缓进入训练，不改标签。完成8个防御/等量随机删除模型，加上原4组共12个模型；模型文件、清单哈希和逐样本测试指标均核验通过。

| 条件 | 未处理准确率 | 等量随机删除 | 语义筛选后 |
|---|---:|---:|---:|
| clean_subset | 94.44% | 93.84% | 93.95% |
| label_flip_05 | 92.49% | 91.91% | 92.81% |
| label_flip_10 | 89.89% | 89.83% | 93.79% |
| targeted_0_to_1 | 93.03% | 92.95% | 94.08% |

定向飞机→鸟误分类率：未处理10%，随机删除8.875%，语义筛选0.125%。5%/10%随机投毒清单分别移除全部200/400个投毒样本，但同时误隔离53/46个正常样本；定向组移除79个投毒样本、误隔离58个正常样本，剩余1个投毒样本。干净组误隔离60张，准确率从94.44%降至93.95%。

这说明固定防御策略在本轮受控实验中减轻了损害，效果与代价均存在。5%组仅提升0.325个百分点，不能把检测检出率当成性能恢复幅度。本轮是单训练种子和单随机删除种子；随机对照匹配总删除数，未匹配类别分布，尚未进行多种子统计验证。

[完整报告与对照图](../../results/stl10_poisoning/defense_training/defense_report_ZH.md) · [实验协议](DEFENSE_PROTOCOL_ZH.md)

## 多训练种子重复

在已有 seed=2026 的 12 组实验基础上，新增 seed=2027、2028，共 36 个模型。固定数据划分、投毒和防御选择，只改变训练随机性。详细协议见 [防御实验协议](DEFENSE_PROTOCOL_ZH.md)。

从项目根目录启动或恢复：

```powershell
wsl.exe -d Ubuntu-24.04 -- /home/anima/.venvs/s6-training/bin/python -u s6/data_poisoning/train_stl10_multiseed.py
```

完成进度保存在 `results/stl10_poisoning/multiseed_training/progress.json`。全部完成后自动校验并生成该目录下的 `multiseed_report_ZH.md`，包含三种子的均值、样本标准差和同一种子内的配对防御增益。尚未完成全部模型时不生成汇总结论。

## 小组实蝇数据

已新增独立的5类实蝇图像实验入口，保留STL-10对照。数据审计、推断编号分组、完整训练范围和运行命令见 [实蝇实验协议](FRUITFLY_PROTOCOL_ZH.md)。

## 标本分组防御扩展

新增按标本隔离的检测器开发与12组分类对照，保留首轮结果。详见[标本分组防御协议](FRUITFLY_GROUPED_DEFENSE_ZH.md)。
