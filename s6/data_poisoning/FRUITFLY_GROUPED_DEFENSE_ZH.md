# 实蝇标本分组检测与防御训练 v1

本轮以同学提供的5类实蝇图片为主实验，保留STL-10及旧实蝇检测结果。复用已核验的干净分类模型，新训练11个模型，共12个条件。

## 检测器完善

- 以用户确认的文件名前9位标本编号分组；编号哈希仅用于分组，不作为分类特征。
- 5折按标本划分。待检测标本的任何图片均不参与该折的分类器拟合、近邻或类别中心计算。
- 近邻从不同参考标本中各取一张最近图片，最多15个标本，避免同一标本多视角占据多数投票。
- CLIP特征固定；逻辑分类器参考样本按标本数量加权并平衡候选类别。类别中心及距离尺度只在参考折计算。
- 检测器只接收sample_id、图片哈希、候选标签和不透明标本组ID，不接收原标签或投毒真值。

## 预先固定的开发协议

用原分类验证集1392张图片（60个标本）开发检测器，构造开发投毒seed=52026/52027，分别5%、10%随机翻转及0→1源类20%定向翻转。测试集1321张不参与特征参考、阈值和权重选择。原分类训练集6531张是后续防御处理对象。

候选C为1、10；近邻/分类器/中心权重为(.4,.4,.2)、(.25,.75,0)、(0,1,0)、(.5,.5,0)。阈值从0.30到0.975，步长0.025，另有全部放行选项。约束开发干净误报率<=5%，最大化六种开发攻击的平均F1；并列时优先更低误报、更高阈值。

开发集标签用于构造及评分开发攻击，这是明确的监督校准；最终训练候选的隐藏投毒真值不用于参数或隔离选择。所有训练候选判定、语义与随机删除清单冻结以后才打开真值评分。

该验证集也用于下游分类模型选检查点。它不是第二个独立测试集；最终测试保留。既有实蝇攻击结果已看过，不宣称全新盲测。干净开发误报约束不是实际部署保证。

## 下游训练对照

4个数据条件：干净、5%翻转、10%翻转、定向correcta→zonata。每个条件3种策略：未处理、语义隔离、等量随机删除。仅保留ALLOW，不纠正标签；随机删除种子固定32026+条件索引。

原干净ResNet18模型复用；其余11个沿用seed2026、20轮、batch32、ImageNet预训练、AdamW和余弦学习率。只按验证Macro-F1选检查点，完整测试1321张。所有组训练超参数一致；各组样本数不同意味着优化更新次数不同，随机对照只匹配删除总数，未匹配类别/标本分布。

## 运行与产物

从项目根目录使用WSL GPU Python：

```powershell
wsl.exe -d Ubuntu-24.04 -- /home/anima/.venvs/s6-training/bin/python -u s6/data_poisoning/prepare_fruitfly_grouped_defense.py
wsl.exe -d Ubuntu-24.04 -- /home/anima/.venvs/s6-training/bin/python -u s6/data_poisoning/train_fruitfly_defense.py
wsl.exe -d Ubuntu-24.04 -- /home/anima/.venvs/s6-training/bin/python -u s6/data_poisoning/report_fruitfly_defense.py
```

- `data/fruitfly_poisoning/grouped_defense_v1/`：冻结协议、开发划分、参数选择和防御候选清单。
- `results/fruitfly_poisoning/grouped_defense_v1/`：检测判定、隔离评分、training_progress.json、模型测试结果和完成后的defense_report_ZH.md。
- WSL `~/s6-training-artifacts/fruitfly/grouped_defense_v1/`：模型与训练日志。

训练入口跳过已完成且符合协议的模型，未完成模型从头训练。每完成一组更新进度；发生错误写training_failure.json，不把失败当完成。全部12组齐全后自动重算逐样本测试指标和隔离代价。当前为单种子实验，后续如要声明稳定性需另做重复。
