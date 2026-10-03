# 本轮工作总结（2026-10-03，提示词注入）

本轮从“表示/标注一致性审计”出发，最后转向调用级任务对齐。所有测试集都按“先冻结、只评估一次”的方式使用；文中标为“诊断”的结果用的是已曝光数据。前端、P3、检测器和实蝇部分均未改动，也没有提交。

## 1. 主要结论（可直接用于汇报）

1. **主 baseline 对 BIPIA 过拟合。** P1/P2/混合系统冻结后直接用于 InjecAgent，检出率只有 3.70%/0.19%/3.89%；在 NotInject 上，P1 误报 16.81%。在 BIPIA 上，对应数字是 93–97% 的检出率和 2–4% 的误报率。[报告](../results/bipia/baseline_cross_source_v1/report_ZH.md)
2. **关系抽取研究线：v3 标注规范在新数据上没有独立增益。** 在密封留出组上，28 组 v3 不计 claims 的匹配单元为 21/60，v1 为 23/60；验证集上的提升属于乐观偏差。数据规模的收益在新数据上保持（9→15→21）。判定层面，v3 与 v1 都是 16/18，v3 的错误全部来自输出格式无效。[报告](../results/bipia/relation_v3_evaluation/holdout/report_ZH.md)
3. **调用级任务对齐在两个外部数据集上有效。** 方法不看正文怎么措辞，只比较用户任务与拟执行的结构化工具调用：
   - InjecAgent（测试集一次）：攻击调用自动放行 126/423 → 1/423，越权读取 126/144 → 1/144；正常调用自动放行 9/9 → 6/9。[报告](../results/bipia/call_alignment_v1/report_ZH.md)
   - AgentDojo（测试集一次，加参数来源检查）：P3＋对齐把 110/164 条攻击写入直接拒绝；研究变体中，正常任务全自动完成 21/49 → 40/49，攻击被完整放行 11 → 14/153。[报告](../results/bipia/agentdojo_alignment_v1/report_ZH.md)
   - v2 修复了网页读取和误拒（已曝光诊断）：P3＋对齐的攻击完整放行 11 → 0。[诊断](../results/bipia/agentdojo_alignment_v2_diagnostic/report_ZH.md)
4. **适用范围（负面结果）**：在 ASB 上，攻击工具与任务同主题，语义相似度无法区分正常工具和攻击工具（测试集：正常放行 21%，任务全自动 0/26）。[报告](../results/bipia/asb_alignment_v1/report_ZH.md)

一句话：**基于内容的检测换了数据来源就失效；基于调用的确定性约束（P3、任务对齐、参数来源）跨来源有效，但拦不住同主题的恶意工具，也管不到不涉及工具调用的注入。**

## 2. 新增产物

- 代码（`s6/prompt_injection/`）：`relation_annotation_audit_v1`、`relation_contract_v3`、`relation_targets_v3`、`relation_sft_v3_io`、`experiment_relation_scale_training_v3`、`evaluate_relation_v3`、`verify_relation_v3`、`relation_comparator_v1`、`score_relation_decisions_v1`、`evaluate_baseline_cross_source_v1`、`call_alignment_v1`、`agentdojo_alignment_v1/v2`、`asb_alignment_v1` 及对应的 prepare/evaluate 入口；均已登记到工程检查，并有契约测试。
- 数据（`data/bipia/`）：`relation_scale_targets_v3`、`relation_scale_training_v3`、`relation_holdout_v3(_candidates)`、`relation_comparator_v1`、`call_alignment_v1`、`agentdojo_alignment_v1`、`asb_alignment_v1`；导航见 [INDEX_ZH.md](../data/bipia/INDEX_ZH.md)。
- 外部来源（`external/`，已被 gitignore）：AgentDojo v0.1.35（commit `a75aba76`，MIT）、ASB（commit `544540ff`，仅 `data/`，MIT）。WSL 中新增独立环境 `~/.venvs/agentdojo`。
- 方向文档：[RESEARCH_DIRECTIONS_2026-10-03_ZH.md](RESEARCH_DIRECTIONS_2026-10-03_ZH.md)。

## 3. 已曝光、不能再作为独立测试的数据

关系抽取的验证集和密封留出组；InjecAgent 与 NotInject（P1/P2 跨来源评估及调用对齐测试）；AgentDojo v1.2.2 的两个划分；ASB 的两个划分。

## 4. 待用户决定

1. **提交**：本轮所有改动都没有提交。8 个含人工审核记录的数据目录不在 git 中（见 INDEX 第 6 节）。按约定，用户说“确认提交”后，只提交本轮讨论过的文件，不使用 `git add -A`。
2. **后续方向**（任选）：
   - 用约束解码消除关系抽取的无效输出（需要新的未曝光数据）；
   - 在 P3 之上做参数来源检查 P3.2（会涉及 P3，需批准）；
   - 用可信的“任务-工具清单”应对 ASB 这类同主题攻击；
   - 把调用级对齐的结论接入前端展示（会改前端，需批准）。
