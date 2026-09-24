# IP102 图片数据投毒 Base

这个 base 演示 S6 安全层如何在模型训练或数据摄取之前验证候选训练数据。它会生成受控的 IP102 标签投毒清单，与独立可信清单进行比较，并通过本地 Python 后端和浏览器前端展示结果。

## 目录结构

```text
data_poisoning/
├─ app.py                       本地 HTTP 后端
├─ integrity_detector.py        清单完整性判定策略（D0）
├─ manifest_protocol.py         D1 候选清单／隐藏真值文件级隔离协议
├─ semantic_detector.py         语义标签异常判定策略（D2），对隐藏答案盲评
├─ prepare_ip102_poisoning.py   生成干净和投毒清单
├─ evaluate_manifests.py        integrity_detector.py 的批量评估
├─ evaluate_semantic.py         semantic_detector.py 的批量评估
├─ train_ip102_models.py        五分类 ResNet18 模型行为实验
├─ verify_training_environment.py  WSL/CUDA 训练环境自检
├─ requirements-windows.txt     torch/torchvision（CPU 版）+ scikit-learn + pillow + open_clip_torch
├─ requirements-training-linux.txt  WSL/Linux GPU 训练依赖
├─ tests/                       协议、完整性与语义检测单元测试
├─ start.cmd                    当前 base 的双击启动入口
└─ web/
   └─ index.html                浏览器前端
```

大型数据和生成结果放在代码目录之外：

```text
external/IP102/                        不可修改的约 3 GB 原始数据
external/clip_cache/                   缓存的 CLIP ViT-B/32 预训练权重（约 580 MB）
data/ip102_poisoning/manifests/        只含可摄取字段的候选 CSV 清单
data/ip102_poisoning/hidden_ground_truth/  只供冻结预测后评分的隐藏真值
data/ip102_poisoning/embeddings/       缓存的 CLIP ViT-B/32 图片特征（按 sha256 索引）
results/ip102_poisoning/               数据集及样本级检测结果
results/ip102_poisoning/model_training/  小型训练摘要、曲线和逐样本预测
~/s6-training-artifacts/               WSL/D 盘上的 checkpoint 与 TensorBoard 日志
```

程序不会覆盖 IP102 原始图片。标签投毒只修改生成清单中的 `assigned_label`。

## 快速启动前端和后端

双击本目录下的 `start.cmd`，或在终端中直接运行它。

第一次运行时，如果清单不存在，启动器会自动生成。后端随后运行在：

```text
http://127.0.0.1:8766
```

浏览器会自动打开前端。使用时保持终端开启；需要停止时在终端按 `Ctrl+C`。
前端会先显示快速的清单完整性结果，再加载语义摘要。正式评估生成的
`semantic_sample_results.json` 会被后端直接读取，因此启动页面不会重新拟合 NCA。

### 前端如何使用

1. 查看页面顶部四个数据集的整体判定——每张卡片同时展示完整性检测徽章和语义检测徽章。
2. 选择干净清单、5% 翻转、10% 翻转或定向投毒清单。
3. 点击“随机查看样本”。
4. 对比可信原始标签和候选训练标签。
5. 查看真实 IP102 图片、SHA-256、完整性判定和说明；下方还有语义检测判定、风险分数、原因和最近邻样本。
6. 可以连续随机抽样，不必重启后端。

在投毒清单中，随机抽样会优先选择标签发生变化的记录，方便观察。图片本身可能完全正常，因为标签投毒修改的是训练元数据，而不是图像像素。

## 手动启动后端

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\app.py'
```

可选参数：

```text
--port 8766       修改本地端口
--no-browser      只启动后端，不自动打开浏览器
```

### 后端接口

#### `GET /api/summary`

重新评估所有候选清单，返回数据集判定、风险分数、标签变化、哈希变化、缺失/未知样本、重复标识和类别分布漂移。

#### `GET /api/sample?dataset=label_flip_05`

从指定数据集中随机返回一个样本，包括可信标签、候选标签、哈希状态、类别名称和安全的本地图像地址。

#### `GET /api/image?sample_id=...`

只有样本属于可信实验子集时才返回图片。路径验证可防止接口读取任意本地文件。

#### `GET /api/semantic?dataset=label_flip_05`

优先读取与当前检测器配置哈希匹配的预计算结果，返回指定数据集的
`ALLOW`/`REVIEW`/`QUARANTINE` 判定分布、平均风险分数和检测器元数据。
预计算文件不存在或版本不匹配时，才回退到现场运行 `semantic_detector.py`。

`GET /api/sample` 的返回体也会附带该样本的 `semantic` 字段：判定、风险分数、可读原因、最近邻样本的候选标签与距离，以及原始信号值（`neighbor_label_agreement`、`classifier_confidence`、`centroid_distance_z`）。

前端不负责决定数据是否安全。所有结果均由后端调用 `integrity_detector.py` 和 `semantic_detector.py` 产生，前端只负责展示。

## 生成实验数据

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\prepare_ip102_poisoning.py'
```

实验使用固定随机种子、五个类别和每类 200 张训练图片：

- `clean_subset`：1,000 条可信记录
- `label_flip_05`：50 条随机标签变化
- `label_flip_10`：100 条随机标签变化
- `targeted_0_to_1`：40 条类别 0 被修改为类别 1

生成器执行 D1 文件级盲评协议：

- `manifests/*.csv` 每行严格只有 `sample_id`、`source_relpath`、`sha256`、
  `assigned_label`，检测器和训练程序只能读取这一侧。
- `hidden_ground_truth/*.csv` 单独保存 `original_label`、`poisoned` 和
  `poison_type`，仅评估程序在预测已经冻结之后读取。
- `manifest_protocol.py` 会拒绝候选清单中的任何额外字段；隐藏答案即使被误加回候选 CSV，
  单元测试和运行时加载都会立即失败。

## 批量评估

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\evaluate_manifests.py'
```

检测器无法读取 `poisoned` 答案字段，因为候选清单物理上没有该列；它独立比较样本成员、
SHA-256、标签、重复记录和类别分布。

## 五分类模型行为实验

WSL 训练环境位于 `~/.venvs/s6-training`。完整四组实验命令：

```bash
source ~/.venvs/s6-training/bin/activate
cd /mnt/e/研究生/高级计算机项目
python s6/data_poisoning/train_ip102_models.py --all \
  --epochs 20 --batch-size 32 --workers 4 --seed 2026 --pretrained --amp
```

训练程序通过 `manifest_protocol.load_candidate_manifest()` 读取候选清单；只要 CSV 含有
`original_label` 或 `poisoned` 等额外字段就拒绝启动。模型使用相同的 ImageNet 预训练
ResNet18、初始化种子、增强、AdamW 和余弦学习率计划，验证与测试来自 IP102 官方、与训练
分离的 `val.txt`/`test.txt`。checkpoint 和 TensorBoard 日志默认写到 WSL 虚拟磁盘所在的
`~/s6-training-artifacts/`，避免继续占用仅剩约 40 GB 的 E 盘；E 盘只保存约 0.5 MB 的
历史、预测与 JSON 摘要。

### 首轮真实测量结果（seed=2026）

| 训练候选清单 | 测试准确率 | Balanced accuracy | Macro-F1 | 真类 0→预测类 1 | 准确率相对干净组 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `clean_subset` | 0.6924 | 0.6859 | 0.6835 | 0.1134 | — |
| `label_flip_05` | 0.6452 | 0.6490 | 0.6399 | 0.1313 | -0.0472 |
| `label_flip_10` | 0.6642 | 0.6654 | 0.6520 | 0.1254 | -0.0281 |
| `targeted_0_to_1` | 0.6407 | 0.6742 | 0.6502 | 0.3104 | -0.0517 |

定向组最重要的结果不是总体准确率，而是类别 0 被预测成目标类别 1 的比例从干净模型的
11.34% 升到 31.04%，增加 19.70 个百分点。两个随机翻转结果在单一 seed 下没有呈现严格的
剂量单调性（10% 组反而略好于 5% 组），所以这是一轮可复现的初始测量，不是统计显著性结论；
后续应至少增加多个训练 seed，报告均值、标准差和置信区间。

完整汇总位于 `results/ip102_poisoning/model_training/comparison_summary.json`，每组目录还包含
训练历史、验证/测试逐样本预测和完整混淆矩阵。

## 语义标签异常检测器（D2）

`integrity_detector.py` 只在存在可信基准清单时才有效——它本质是一个 diff 工具，不检查图片内容本身。`semantic_detector.py` 则相反：不依赖任何可信清单，直接判断图片像素内容是否符合它声称的候选标签。

它在接口和文件两层都对隐藏答案“盲”：其输入类型 `SemanticInputRecord` 只有
`sample_id`、`source_relpath`、`sha256`、`assigned_label` 四个字段；检测器读取的候选 CSV
也严格只有这四列。`evaluate_semantic.py` 先只加载候选文件并冻结全部判定，之后才打开
`hidden_ground_truth/*.csv`，按 `sample_id` 校验一一对应后用于打分。模块断言、严格 CSV
schema 和单元测试共同守护这一约定，D1 文件级拆分现已完成。

### 安装额外依赖

基础依赖（`bipia` 自身的依赖）不包含视觉模型栈。在共享 venv 中安装 CPU 版 PyTorch/TorchVision、scikit-learn、Pillow 以及 open_clip：

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' -m pip install torch torchvision `
  --index-url https://download.pytorch.org/whl/cpu
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' -m pip install `
  -r 'E:\研究生\高级计算机项目\s6\data_poisoning\requirements-windows.txt'
```

这里有两次一次性下载：CPU 版 PyTorch 轮子约 300–400 MB；`extract_embeddings()` 第一次运行时还会再下载约 580 MB 的 CLIP ViT-B/32（OpenAI 权重）预训练模型。两者都会被缓存——PyTorch 轮子留在 venv 里，CLIP 权重则通过 `cache_dir=` 参数重定向缓存到 `external/clip_cache/`，不会落到用户级默认目录 `%USERPROFILE%\.cache\huggingface\`，以符合本仓库“所有不可变的第三方下载都放在 `external/` 下”的约定。

### 工作原理

1. `extract_embeddings()` 用一个冻结的预训练 CLIP ViT-B/32 图像编码器（`open_clip`，OpenAI 权重，quick-GELU 变体以匹配原始权重）对每张唯一图片提取 512 维特征，按 SHA-256 缓存到磁盘——四份清单共用同一批 1,000 张图片，因此只需付出一次 CPU 推理成本。此版本替换了早期的 ResNet18/ImageNet1K 版本（检测器 `0.1.0`）：通用 ImageNet 监督特征在这五个细粒度害虫类别上区分度不够，因此 `0.2.0` 换用 CLIP 的对比学习特征，测试其是否能把这五类分得更开（结果没有，见下文）。
2. `fit_trusted_projection()`（检测器 `0.3.0`，`0.4.0` 中修订）只在 `clean_subset.csv` 的可信 `assigned_label` 上——也就是 `integrity_detector.py` 已经当作可信基准的那份清单——拟合一个投影，采用 5 折分层交叉验证，保证每张可信图片的投影特征都来自一个从未见过该图片的模型。`0.3.0` 用的是 `LinearDiscriminantAnalysis`，被限制在 `n_classes - 1 = 4` 维；`0.4.0` 换成了 `NeighborhoodComponentsAnalysis`（NCA），它直接优化 soft k-NN 分类目标（正好对应下面最近邻一致性信号实际需要的东西），且不受类别数限制，因此投影到 `PROJECTION_COMPONENTS = 32` 维。这就是"在可信干净子集上做微调/度量学习"这一步,每次运行都重新计算(不额外缓存——在 1,000 个 512 维向量上拟合速度很快)。由于每份候选清单共用同一批 1,000 张图片(只有 `assigned_label` 不同),这一次可信拟合就能覆盖所有样本的投影特征。
3. `assess_semantic()` 组合三个独立信号,现在都基于投影后的特征而非原始 CLIP 特征计算:
   - **最近邻标签一致性**——对特征做余弦距离 k-NN（`k=15`），统计每个样本的最近邻中有多少比例与其候选标签一致。
   - **交叉验证分类器分歧**——用 `LogisticRegression` 做 5 折分层 out-of-fold 预测（`cross_val_predict`），保证没有样本被自己训练出来的模型评分；记录模型对候选标签的置信度。
   - **类别中心距离**——样本到其候选类别（留一）中心的距离，相对该类别典型距离分布做 z-score。
4. 三个信号加权（`neighbor_disagreement` 0.4、`classifier_disagreement` 0.4、`centroid_distance` 0.2）得到 `risk_score`，按阈值判定为 `ALLOW`（`< 0.62`）/ `REVIEW`（`< 0.75`）/ `QUARANTINE`（`>= 0.75`）。

### 运行评估

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\evaluate_semantic.py'
```

会写出 `results/ip102_poisoning/semantic_assessments.csv`（数据集级指标）、
`semantic_flagged_samples.csv`（每个被标记为 `REVIEW`/`QUARANTINE` 的样本，包含误报，供人工检查）、
`semantic_evaluation_summary.json`，以及供本地控制台快速查询全部 4,000 条检测结果的
`semantic_sample_results.json`。

### 真实测量结果

在真实的 1,000 张图片、5 类 IP102 子集上测得（`REVIEW_THRESHOLD=0.62`、`QUARANTINE_THRESHOLD=0.75`，阈值是根据 clean_subset 的风险分数百分位数选取的，没有用单个样本的投毒标签去调参），使用可信标签 NCA 投影 + CLIP ViT-B/32 特征（检测器 `0.4.0`）：

| 数据集 | ALLOW | REVIEW | QUARANTINE | 精确率 | 召回率 | F1 | 干净误报率 | ROC-AUC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `clean_subset`（0% 投毒） | 662 | 234 | 104 | — | — | — | 0.338 | — |
| `label_flip_05`（5%） | 646 | 246 | 108 | 0.102 | 0.72 | 0.178 | 0.335 | 0.740 |
| `label_flip_10`（10%） | 620 | 262 | 118 | 0.179 | 0.68 | 0.283 | 0.347 | 0.780 |
| `targeted_0_to_1`（约 4%） | 646 | 238 | 116 | 0.040 | 0.35 | 0.071 | 0.354 | 0.538 |

**这是第三个持平/混合结果——把 LDA 换成 `NeighborhoodComponentsAnalysis` 并没有追回原始 CLIP 特征的基线水平（检测器 `0.2.0`：精确率 0.057–0.216，召回率 0.425–0.79，ROC-AUC 0.647–0.805），相比 LDA 投影（检测器 `0.3.0`：精确率 0.029–0.208，召回率 0.225–0.75，ROC-AUC 0.570–0.802）也只是部分改善。** NCA 确实找回了一些 LDA 丢失的召回率（`targeted_0_to_1` 从 22.5% 提到 35%，`label_flip_05` 从 64% 提到 72%），这两个数据集上的精确率/F1 也略有提升。但 `label_flip_10` 在每一项指标上都比 LDA 更差（精确率 0.208 → 0.179，召回率 0.75 → 0.68，ROC-AUC 0.802 → 0.780），四个数据集的干净误报率普遍略微上升（均值约 0.34，高于 LDA 的约 0.33），而 `targeted_0_to_1` 的 ROC-AUC 仍接近随机猜测（0.538，比 LDA 本就不理想的 0.570 还略低，远低于原始 CLIP 的 0.647）。在三个投毒数据集上取平均，NCA 的平均 ROC-AUC（0.686）低于 LDA（0.708），两者都低于原始 CLIP（取其区间中点约 0.706）。这说明此前对 LDA 结果的诊断只对了一半：NCA 确实修正了”优化目标不对”这一半（它直接优化 k-NN 式的近邻一致性），也因此带来了真实的召回率提升，但去掉 `n_classes - 1` 的维度上限并没有换来更好的整体区分度。结合此前 CLIP 与 ResNet18 的对比结果以及 LDA 的结果，这已经是连续三次尝试改造嵌入空间（换主干网络，再换两种不同的可信标签投影），却都未能让 ROC-AUC 和精确率明显超过最初原始 CLIP 的测量结果——有力地说明瓶颈根本不在嵌入/投影方式的选择上，而在于这三个信号本身依赖的通用距离/近邻结构，在这五个视觉上相近的害虫类别上，无论用什么冻结的、非端到端训练的特征都撑不起来。要进一步突破，大概率需要一个针对这个具体分类任务端到端训练的模型，这已经超出了本 baseline 的范围。

上段所说“超出 baseline 范围”特指用端到端模型替换 D2 异常检测器；本轮新增的 ResNet18
训练则把端到端模型作为**下游受害模型**，用于测量标签投毒造成的行为影响，两者角色不同。

“被标记”指判定为 `REVIEW` 或 `QUARANTINE`（即非 `ALLOW`）。精确率/召回率/F1 是对照独立
隐藏真值中的 `poisoned` 字段计算的，但该文件只在检测器判定被冻结**之后**才被读取——见
`evaluate_semantic.py`。

**请仔细看这些数字——这个检测器是一个真实但有噪声的信号，在这个规模下还不是可靠的分类器。** 即使是标注完全正确的 IP102 图片，在这套流程下看起来也很模糊：在全干净的 `clean_subset` 上，`REVIEW` 档的干净误报率约为 34%。两个随机翻转数据集的召回率还算可以（68–72%），但定向翻转数据集的召回率明显下降（35%，仍低于加入投影之前测得的 42.5%），ROC-AUC 范围是 0.54–0.78——随机翻转场景仍有实质区分度，但定向翻转场景已经接近随机猜测。精确率整体偏低（4.0–17.9%），意味着大多数单条 `REVIEW`/`QUARANTINE` 标记其实是需要人工排查的误报。这个检测器更适合当作”优先复核”信号，而不是可以自主执行隔离的判定。

## 安全与研究限制

- 精确识别标签变化需要一份独立、可信且受访问控制保护的基准清单；如果攻击者能同时修改两份清单，直接比较将失效。
- 仅靠类别分布漂移无法证明单个标签是否正确。
- 语义检测器的交叉验证分类器和类别中心都是在候选清单*自身*的标签上拟合的。投毒比例非常高时，这份参照统计本身就会被污染——目前只在 10% 随机翻转和约 4% 定向翻转的比例下做过测量，没有测过多数样本被投毒的情况。
- 语义检测的精确率偏低（实测 4.0–17.9%，见上文）——实际部署应该把它当作人工复核队列的优先级排序信号，而不是可以独立执行隔离的判定。三次连续尝试改造嵌入空间——把特征提取器从 ResNet18/ImageNet1K 换成 CLIP ViT-B/32、在可信干净子集上做 LDA 投影（检测器 `0.3.0`）、再换成 NCA 投影（检测器 `0.4.0`）——都没有明显改善这一点；定向翻转场景尤其明显，三次嵌入方式的改动下 ROC-AUC 始终徘徊在接近随机猜测的 0.54–0.65 区间。这种模糊性看起来是这五个类别在任何冻结的、非端到端训练特征下的固有属性，而不是这个 baseline 的信号能修正的嵌入空间问题。
- D1 已实现文件级隔离，但 `hidden_ground_truth/` 目前只是实验目录分离，并不是操作系统级访问控制；生产环境仍需为评分账户与训练账户配置不同权限。
- 当前版本已测量标签投毒对模型行为的影响；像素后门仍需要额外的图像变换、触发器检测和攻击成功率实验。
- 模型行为表目前只有一个训练 seed；它能证明本次可复现实验中的影响，不能估计跨 seed 方差或统计显著性。
- 生产环境还应使用签名清单、基于角色的访问控制、不可修改审计日志、隔离、审批和回滚。
- 服务只绑定 `127.0.0.1`，且只允许读取可信子集中的图片。

英文说明见 [README.md](README.md)。

后续里程碑见 [../BASELINE_ROADMAP_ZH.md](../BASELINE_ROADMAP_ZH.md)。
