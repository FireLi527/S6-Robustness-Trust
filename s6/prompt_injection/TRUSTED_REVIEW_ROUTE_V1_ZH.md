# 可信任务分工开发回放 v1

本候选融合两个同一Qwen3-4B的冻结提示词头：原始任务/正文判定＋编号证据，以及初版改写提示词＋编号证据。它不是新增分类器训练，也不使用v2/v3提示词输出。

公开规则在`trusted_review_route_v1.py`；编排和核验在`experiment_trusted_review_route_v1.py`。前者只依赖Python标准库；后者读取公开消息构造、证据解析、汇总和工程原子产物模块，不导入其他实验脚本。

## 复现

从仓库根目录使用WSL GPU环境的Python（核验需本地分词器，不运行GPU推理）：

```text
python -m s6.prompt_injection.experiment_trusted_review_route_v1 --stage run
python -m s6.prompt_injection.experiment_trusted_review_route_v1 --stage verify
```

已有运行目录独占，命令不得覆盖。变更规则或重新运行需新模块与独立实验目录；当前输入、代码、模型与来源输出均已冻结。

输入545条取自`data/bipia/reviewer_refinement_v2/rows.json`：共享真实任务/正文、339条固定引用压力、中文诊断、旧任务互换和32条新审核对照。读取v2的数据不使用v2的模型输出。两个头的来源为已核验的消融、初版完整压力、初版审核对照结果；固定最早记录优先，不按正确性择优。

## 规则与限制

仅可信task进入选择器：同时具有quoted、explain/translate/analyze与do not perform/execute/carry out的任务，或第一人称“I authorize”声明，选择初版both；其他任务选择evidence_only。可信task明确包含先前审批记录不可用、只执行先前批准操作的条件，返回UNKNOWN准备状态，保留模型判断。INVALID送UNKNOWN，任何输出都不授权执行。

当前正则只覆盖窄范围英语文字。此阶段未校验真实审批、未实现完整权限语法和参数溯源，也未作实时集成模型推理。规则解决的是部分明确缺失状态的表达，不应宣称模型的UNKNOWN能力已有提升。

## 检查和结构

路由6项契约测试覆盖可信输入边界、引用条件、缺审批复核、已知记录、INVALID/UNKNOWN和引用描述缺审批。工程检查502项中500通过、2跳过，结果见`results/engineering/checks/20261004T174309Z-c00536c7`。模型输出与路由核验独立于工程测试；没有真实工具或视觉验收。

本轮新增11个运行模块共1086行，最大158行；已登记统一检查。v2/v3保留独立短推理内核和编排副本是冻结实验身份需要，没有修改已经关联哈希的旧入口。重复记录明确保留，后续非冻结运行链路才考虑统一。未跨两条baseline导入业务代码。

研究结论与分母见`results/bipia/trusted_review_route_v1/report_ZH.md`。下一阶段应冻结候选后独立采集材料，不能使用本轮已曝光材料证明泛化。
