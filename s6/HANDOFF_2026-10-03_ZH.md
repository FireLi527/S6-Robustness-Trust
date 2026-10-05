# S6 新对话交接说明

更新日期：2026-10-03。项目根目录：`E:\研究生\高级计算机项目`。用户负责研究生课程项目的 S6 Robustness & Trust。本文是接手导航，实际协议、代码及产物优先。

> **最新进展（2026-10-03 晚）**：本文下方第 2–6 节描述的是本轮开始时的状态。之后已完成：标注审计、v3 契约与重训、密封留出组、主 baseline 跨来源冻结评估，以及在 InjecAgent、AgentDojo、ASB 上的调用级任务对齐。**请先读 [本轮总结](ROUND_SUMMARY_2026-10-03_ZH.md)**，其中列出了结论、新增产物、已曝光的数据和待用户决定的事项（包括尚未提交）。数据目录导航见 `data/bipia/INDEX_ZH.md`。

## 1. 先读什么

**最新：固定v3的未曝光中文受控确认通过（2026-10-05）**。先读[40条首次确认报告](../results/bipia/chinese_analysis_confirmation_v1/report_ZH.md)和[方法](prompt_injection/CHINESE_ANALYSIS_CONFIRMATION_V1_ZH.md)。候选先冻结再编写8组40条新正文，用户全部认可；40条全新推理，五类关系各8/8，中文分析头正常/攻击各8/8。预设研究PASS、技术核验PASS40条，旧609条状态/决策重算零变化，工程539通过/2跳过。模型UNKNOWN0/8，最终UNKNOWN8/8来自审批规则；不授予执行权限。候选可收尾为“新受控材料确认通过”，不能宣称自然分布100%、通用未知授权或真实代理成功率。旧首次确认失败、开发文稿标题误报和旧中文未知诊断保留不改。原准备原子写入接口失败及独立修正版保留。审核已存review目录，不再询问标签；全部输入/输出/核验目录独占，禁止再次run覆盖。无待续跑/审核任务，本轮未部署、训练、提交或推送；前轮已推送dfb8744的事实不变。

**当前进展（2026-10-05 弱项提升完成）**：先读[开发v3报告](../results/bipia/readiness_routing_v3/report_ZH.md)和[方法](prompt_injection/READINESS_ROUTING_V3_ZH.md)。v2补审批缺失改写/分析分工，v3加中文分析头；前组32/32、收尾31/32，最近组UNKNOWN8/8、正常15/16、风险8/8，原545条决策零变化。v2开发FAIL保留，v3开发PASS；各609条技术核验PASS，新增模型推理12+8，工程535通过/2跳过。剩一条文稿标题引用误报；新中文头八条都是正常引用，尚无该头的攻击对照确认。所有材料已曝光，旧中文UNKNOWN仍0/6；下方首次收尾25/32的独立FAIL不能改写。下一步固定候选另备未曝光中文正常引用/改变解释结果的注入/混合执行材料并审核，不能按最后一条继续调参当泛化。旧实验目录独占，禁止重新run覆盖。前轮已推送`dfb8744`至`codex/first-round-accuracy`；本轮未提交/推送、未训练部署、默认前端/P3不变，无待续跑任务。

**当前安排（2026-10-05）**：用户决定将审批缺失改写和中文引用误报留作下一步，先提交并推送当前完整研究产物。此次推送不代表收尾验证已通过，也不部署或替换默认检测器；后续不得在原失败目录重跑覆盖。

**2026-10-05 收尾验证完成，尚不满足验证成功条件**：先读[收尾确认报告](../results/bipia/approval_readiness_validation_v1/report_ZH.md)。候选先冻结，8组32条新材料用户全部认可，首次推理及核验完成。最终25/32、风险8/8、正常13/16、UNKNOWN4/8；英文UNKNOWN2/4、中文正常5/8/UNKNOWN2/4，未过门槛。旧577条状态和决策逐条重算不变，前序效果无回退；技术核验PASS、研究门槛FAIL，工程521通过/2跳过。`closure_decision.json`为NOT_READY_TO_CLOSE_AS_VALIDATED_CANDIDATE，不能据开发31/32改写为验证成功。新标签审核保存在`data/bipia/approval_readiness_validation_review_v1/human_review.json`，不再询问。当前候选和失败输出不变，无待续跑、训练、部署或提交；后续如继续，需新版本改善审批缺失改写/中文引用分析，当前32条只能作开发回归，再另取新材料确认。

**2026-10-05 审批准备状态层已完成**：用户要求尽量保留前序效果，已实现独立`approval_readiness_v1.py`，实验`experiment_approval_readiness_v1.py`。先读[最新报告](../results/bipia/approval_readiness_v1/report_ZH.md)及[方法](prompt_injection/APPROVAL_READINESS_V1_ZH.md)。577条开发回放及核验完成：前545条不变，新32条6条UNKNOWN正确转复核，25/32→31/32、UNKNOWN2/8→8/8；风险8/8和正常15/16保留，原模型信号/选头不变，无RISK转NORMAL，无执行授权。模型UNKNOWN仍0/8、旧中文UNKNOWN仍0/6。有限双语规则提取可信任务审批依赖和缺失，以任务SHA与原文证据绑定状态；不代表通用理解、真实权限验证或独立泛化。工程521通过/2跳过，新增模型推理0次，无待续跑任务；未部署、训练、提交。新32条已曝光，本次是开发改进，不能改写下段首次25/32失败结果；后续需新版本及未曝光确认材料。

**2026-10-05 新32条已认可并完成首次确认**：用户明确全部认可，记录在`data/bipia/trusted_route_confirmation_review_v2/human_review.json`，无需再次询问。先读[新双语确认报告](../results/bipia/trusted_route_confirmation_v2/report_ZH.md)：单一原候选保持不变，首次新32条推理最终25/32、风险8/8、正常15/16、UNKNOWN2/8；英文14/16和UNKNOWN2/4，中文11/16和UNKNOWN0/4，完整组2/8。两语言均未过UNKNOWN至少3/4标准，模型UNKNOWN0/8；2条规则UNKNOWN与模型能力分开。完整输出核验PASS、工程507通过/2跳过，无待续跑推理或核验；未训练、部署、提交。后续改进需新版本，将可信任务权限准备状态与正文风险分开；这32条已曝光，后续只能作开发回归。下段“待审核”是准备时历史状态，不能重复索要认可。

**2026-10-05 后续集成已完成**：先读[集成新推理报告](../results/bipia/trusted_review_live_v1/report_ZH.md)。固定路由与两个提示词头，545条重新生成，最终决策与旧回放逐条一致，核验PASS；工程507通过、2跳过。545条是历史曝光回归，不能包装为独立确认。另8组32条新双语控制材料已准备，`data/bipia/trusted_route_confirmation_candidates_v2/REVIEW_ZH.md`待用户审核，尚未评分，不得把旧审核认可应用于新材料。确认入口`experiment_trusted_route_confirmation_v2.py`已登记检查；直接用户审核记录需保存于独立`data/bipia/trusted_route_confirmation_review_v2/human_review.json`（候选哈希、明确labels、approved_ids和authority），之后依次prepare/run/verify，保持原路由，不按新结果改规则冒充确认。没有待续跑的集成推理，未训练、部署、提交；下段“未做集成新推理”属于本次运行前状态。

**2026-10-05 最新进展**：用户已阅读并认可8组32条语义标签，审核记录在`data/bipia/reviewer_confirmation_v1/human_review.json`，无需再次询问。四组消融、完整引用压力、新对照以及v2/v3改进均完成，2509次新推理核验PASS。先读[可信任务分工报告](../results/bipia/trusted_review_route_v1/report_ZH.md)：路由回放InjecAgent58/64、SecOPD33/40及正常误报1/40、引用压力误报12/339；32条最终策略全对，但UNKNOWN8/8来自缺审批规则，模型UNKNOWN0/8，中文UNKNOWN0/6。v2/v3高召回伴随引用压力高误报，失败版本保留。路由为已曝光数据的545条缓存开发回放，未做集成新推理或独立盲测。工程500通过、2跳过，无待续跑推理；前端/P3和默认检测器未改，未训练、部署、提交。后续先固定候选、补集成推理与独立新审核材料，参数来源/能力链路仍未实现。下方“当前没有获批新实验”及旧指标属于前序历史状态。

**2026-10-04 融合尝试已完成**：先读 [融合压力报告](../results/bipia/content_fusion_v1_compat/report_ZH.md)。ProtectAI＋4B并集提升共享攻击检出至62/64及37/40，但339条固定引用任务压力误报48.38%；一致才自动误报7.08%、复核56.64%、正常自动36.28%。两种规则均失败，不部署。原入口在WSL路径解析失败，独立兼容运行完成，原冻结协议与代码保留；339条新推理、每臂483条融合重放PASS，工程486通过、2跳过。参数来源/能力约束仍未新增实现。本轮文件尚未提交。

**2026-10-04 Prompt Guard 后续**：用户本地下载22M版，授权改名与使用，已保存为 `external/llama_prompt_guard_2_22m`；权重、配置和分词器身份核验通过。沿用上轮冻结英文数据与方法，1485条推理及结果核验完成，工程479通过、2跳过。InjecAgent全量召回1.42%，NotInject误报0.59%，SecOPD召回35%且正常误报0%；未达到召回门槛，不替换默认检测器。直接API与扫描器分数对照一致，详见 [最新报告](../results/bipia/prompt_guard_2_v1/report_ZH.md)。本轮文件尚未提交，第三项仍未实施；下段为公开ProtectAI阶段。

**2026-10-04 最新补充**：专用分类器（公开ProtectAI）与基础4B任务/正文直接判定均已完成，结果见 `results/bipia/content_probe_v1_compat/report_ZH.md`。两项比旧Hybrid明显改善，但均未过完整经验门槛；全量分类器压力误报43.36%，4B中文未知授权0/6且原文证据存在无效输出。主评估及任务变化对照核验通过，最终工程479通过、2跳过。第三项参数来源/能力约束只有离线设计建议，尚未实施；现有P3与前端不变。本轮新增文件尚未提交。旧第2–6节不是当前状态。

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
