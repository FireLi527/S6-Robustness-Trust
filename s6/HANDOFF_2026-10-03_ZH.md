# S6 新对话交接说明

更新日期：2026-10-03。项目根目录：`E:\研究生\高级计算机项目`。用户负责研究生课程项目的 S6 Robustness & Trust。本文是接手导航，实际协议、代码及产物优先。

> **最新进展（2026-10-03 晚）**：本文下方第 2–6 节描述的是本轮开始时的状态。之后已完成：标注审计、v3 契约与重训、密封留出组、主 baseline 跨来源冻结评估，以及在 InjecAgent、AgentDojo、ASB 上的调用级任务对齐。**请先读 [本轮总结](ROUND_SUMMARY_2026-10-03_ZH.md)**，其中列出了结论、新增产物、已曝光的数据和待用户决定的事项（包括尚未提交）。数据目录导航见 `data/bipia/INDEX_ZH.md`。

## 1. 先读什么

按顺序读取：

1. `s6/AGENTS.md`、`s6/ENGINEERING_ZH.md`。
2. `s6/BASELINE_ROADMAP_ZH.md` 最新部分；下方历史快照不要当作当前进度。
3. `results/bipia/relation_scale_evaluation_v1/report_ZH.md`、`summary.json`、`verification/result.json`。
4. `s6/prompt_injection/RELATION_SCALE_EVALUATION_V1_ZH.md`、`RELATION_SCALE_TRAINING_V1_ZH.md`。
5. 若开展下一阶段审计，再读 `relation_contract_v2.py`、`relation_sft_v2_io.py`、`relation_scale_targets_v1.py` 和冻结数据中的参考字段。

上述相对路径均相对于项目根目录，不是需要重新生成的文件。

## 2. 当前停在哪里

最近目标“完成扩充训练的五配置开发验证，核验并出报告”已完成。三个训练适配器、五配置推理、产物核验均COMPLETE，不需要续跑本批训练或推理。当前没有获批实施的新一轮实验；最新请求是整理交接，不是追加训练。

用户希望按有终点的目标自主推进，尽量不要每一步都要求“继续”；但需要新的人工语义判断、实质性范围变更时应停下来问。中文沟通，界面和汇报用语简洁；不要把工具/脚本测试称为视觉验收。

## 3. 两条baseline的定位

### 图像数据安全

主线为同学提供的五类实蝇数据，9,244张，按个体划分训练6,531/验证1,392/测试1,321；同一个体不跨划分或折。冻结CLIP特征检测标签异常，ResNet18进行下游分类。STL-10/IP102为历史对照，不回到主线；双翅目/Tephritidae是用户允许的附加研究，不混算实蝇结果。

当前已完成实蝇风险加权和三个种子2026/2027/2028重复。最新报告：`results/fruitfly_poisoning/multiseed_v1/report_ZH.md`。10%随机改标的测试分类准确率均值：未处理97.45%、语义筛选98.28%、风险加权98.11%；定向0→1组：98.54%、98.69%、99.22%。99.22%是分类准确率，不是攻击检出率。条件参考种子2026结果后选定，属于探索性重复，不是独立确认。最近数轮未重新运行图像实验。

单种子原始分组防御结果位于 `results/fruitfly_poisoning/grouped_defense_v1/`；其父目录旧语义结果不能混用。定向0→1错误率分母为干净测试集中真实类别0的图片数。

### 提示词注入

原有P1规则、P2冻结MiniLM语义一致性、Hybrid、P3独立工具权限仍保留。白/黑名单及用户显式批准机制与研究抽取器分离，研究模型不发放权限。意图识别是固定候选任务类型的相似度匹配，不是自由生成精确用户问题。前端已多轮简化，最近研究未替换默认方法，也未改前端或P3。

历史监督分类、SecOPD扩充、跨来源训练及NLI授权关系实验均有冻结报告；同来源指标改善不代表跨来源泛化。入口见里程碑，重要报告在 `results/bipia/secopd_training_v1/`、`cross_source_training_v1/`。数据许可/引用沿用各来源记录，不能将非商用课程用途等同于可任意再分发。

最近主线转为：分别从用户任务与文档抽取动作、对象、条件、缺失信息，再研究授权关系。不是仅根据“删除/上传”等动词判风险。

## 4. 最近数据与训练

- `data/bipia/relation_scale_candidates_v1/`：34任务组、102个核心语义材料（24旧dev2＋78新）、102个Markdown格式变体。
- 核心正常/风险/不确定各34条，用户已完成语义范围及动作审核。新78条的四批记录为 `human_review_01.json` 至 `human_review_04.json`；旧24条审核在 `data/bipia/relation_development_review_v2/human_review.json`。
- 用户没有逐字段审核机器JSON；机器参考为助手转换。102格式变体也不是逐条人工审核的新语义案例。
- `data/bipia/relation_scale_training_v1/`：冻结数据与划分，28训练组168对＝84核心＋84变体；6验证组36对＝18核心＋18变体。父样本/变体/定义的相关任务族不跨划分。
- 验证组：transaction_rollback、retention_cutoff、row_scope、column_projection、cache_namespace、recipient_scope。
- 8/16/28训练组嵌套，含变体48/96/168对，去重后56/112/196份单侧记录。
- 官方本地Qwen3-4B分别从头初始化NF4 LoRA；3轮、种子2026、rank8/alpha16/dropout0.05、q/v投影、lr0.0002、weight_decay0.01、batch1累积4、答案损失。42/84/147优化步，适配器均已保存。
- 训练目录：`results/bipia/relation_scale_training_v1/{small_8,medium_16,large_28}/adapter/`。
- 固定轮数使大数据组同时获得更多计算，不能把差异仅归因于数据量；训练损失下降不等于泛化改善。

六个未来独立任务组/36条材料尚未编写，不要说已具备独立测试结果。旧评估、v1测试和本轮验证均已曝光，不能再次包装为新盲测。

## 5. 最新评估结论

统一比较基础零样本、基础少样本及三个适配器。少样本只用训练示例 `scale-seed-dev2-01`。沿用v2提示与严格评分，贪心1600新token、4096总预算、无输出修复/语法约束、无静默截断。每配置42次独立推理，共210次，显式展开为360条样本侧记录；全部正常EOS。

核心18条材料的任务去重为6条，正文18条，共24个侧输入：

| 配置 | 契约有效 | 任务完整匹配 | 正文完整匹配 | 双侧同时正确 |
| --- | ---: | ---: | ---: | ---: |
| 基础零样本 | 16/24 | 0/6 | 0/18 | 0/18 |
| 基础少样本 | 12/24 | 0/6 | 0/18 | 0/18 |
| 8组 | 22/24 | 0/6 | 0/18 | 0/18 |
| 16组 | 22/24 | 0/6 | 0/18 | 0/18 |
| 28组 | 23/24 | 0/6 | 2/18 | 0/18 |

28组两条核心成功为001和003正文，都在事务回滚组；格式变体复现同两条，不算四个独立成功。核心严格单元精确率/召回率：8组12.20%/10.20%，16组34.88%/30.61%，28组34.09%/30.61%；并非所有指标随规模单调提升。

结论：格式与部分字段改善，但完整双侧抽取仍不可用，不部署。严格评分不是语义等价判断，也不是攻击检出率/FPR/真实代理ASR；不能把0完整匹配解释为每一条完全没理解。

典型诊断：004正文把日期条件放parameter；023正文把全部列放object而非data，信息尚在但表示不同。028任务确实漏掉合成报告；037任务漏掉保留其他命名空间约束。029正文使用契约外copy角色；037正文一边保留映射缺失说明、一边标explicit。既有契约/标注粒度问题，也有真实遗漏，不能一概归因过拟合。

## 6. 建议下一步（尚未实施）

优先“表示/标注一致性审计”，不要立即追加同类数据或重训：

1. 只读检查冻结参考与输出，梳理object/data/source、conditions/constraints、动作拆分/合并、未知状态的规则是否稳定、可复现。
2. 区分信息遗漏、未知信息被补全、语义相近但表示不同。提出少量需要用户判断的规范边界，不让用户重审所有已确认语义标签。
3. 如确需修订契约/训练参考，另开版本并保留本轮原始指标；禁止原位改验证参考后声称模型提升。
4. 规范稳定后才确定新训练范围和冻结协议；再生成/审核未曝光任务组用于独立检验。是否实施新训练由新对话的明确需求决定。

## 7. 代码与复现入口

目录均为 `s6/prompt_injection/`：

- `relation_scale_targets_v1.py`：显式参考字段；`relation_scale_data_v1.py`：审核门禁、转换和分组。
- `prepare_relation_scale_training_v1.py`：数据冻结；`experiment_relation_scale_training_v1.py`：三组训练。
- `relation_scale_metrics_v1.py`：去重分母与汇总；`evaluate_relation_scale_v1.py`：五配置推理；`verify_relation_scale_v1.py`：离线核验。
- 复用冻结 `relation_contract_v2.py`、`relation_sft_v2_io.py`、`relation_sft_v2_evaluation.py`、`relation_sft_runtime.py`，不得原位修改。

上述入口创建独占运行目录，现有训练、评估、核验已COMPLETE。不要再次执行以覆盖或“重试”；只读分析现有产物即可。

结果主目录：`results/bipia/relation_scale_evaluation_v1/`。报告 `report_ZH.md`，指标 `summary.json`，展开输出 `predictions.json`，独立原始输出 `raw/`，凭据 `verification/result.json`。

## 8. 环境、工程约束与工作区

- Windows CPU/测试：`.venv-bipia\Scripts\python.exe`。
- WSL发行版：`Ubuntu-24.04`。本轮LoRA运行环境为项目根目录 `.venv-s6-qlora/bin/python`；复用 `/home/anima/.venvs/s6-training/lib/python3.12/site-packages` 的GPU依赖，不修改原图像训练环境。
- 本地模型：`external/qwen3_4b_train_v1/`，官方Qwen/Qwen3-4B，Apache2；快照与文件哈希以目录记录为准，离线加载。
- RTX5060 Laptop 8GB；勿关闭用户游戏/桌面进程来抢显存，勿随意升级环境。
- 最终质量检查：`results/engineering/checks/20261003T044639Z-e6b93212`，404通过、2项WSL相关跳过。核验210次独立推理、360份展开记录及保护哈希通过。这不是视觉验收。
- 新生产模块登记 `s6/engineering/check.py`；完整检查命令：`.\.venv-bipia\Scripts\python.exe -m s6.engineering.check`。
- 冻结数据、脚本、协议、适配器和哈希关联文件不得原位重构；新行为用新版本。失败记录保留；禁止更新哈希来绕过检查。
- 工作区存在用户既有及研究未提交更改，包括README、里程碑、app、前端和测试等；先看git状态，不回退、不清理、不自动提交或推送，也不要推断所有文件都已纳入Git。
- 本次交接仅改文档，不重跑训练/推理，不改变前端、P3或实蝇。

前端入口保留：根目录 `start.cmd`、`frontend.py`、`index.html`；统一入口8764、提示词8765、图像8766。用户偏好主要结论直观可讲、页面简洁、中英文一致；本次任务不需要改前端或制作PPT。
