> 当前状态（2026-09-25）：图像控制台默认使用**同学实蝇数据集**，STL-10 为可切换的三种子历史对照，IP102 已冻结。里程碑状态见 [BASELINE_ROADMAP_ZH.md](BASELINE_ROADMAP_ZH.md) 顶部快照。

# S6 两个独立安全 Base

后续修改先遵循 [工程标准](ENGINEERING_ZH.md)；统一检查命令为 `python -m s6.engineering.check`（从项目根目录运行）。本轮整改和冻结兼容边界见 [工程审计记录](engineering/AUDIT_ZH.md)。

2026-09-29研究更新：[提示词分块风险聚合实验](../results/bipia/risk_aggregation_v1/findings_ZH.md)已完成。128-token完整分块在开发验证中有局部检出收益，但正常维护文本误报仍高，未证明泛化改善，未替换前端默认模型。

后续[任务边界补充训练对照](../results/bipia/boundary_transfer_v1/findings_ZH.md)已完成六折开发留出：补充审核数据后正文模型误报5/18→0/18、检出8/18→9/18；联合模型有召回代价。材料已被观察过，不能宣称独立泛化提升，未部署。

2026-09-30：[不安全前置条件专项](../results/bipia/prerequisite_training_v1/report_ZH.md)已按12条新审核标签完成。原生校准阈值下风险检出0/7，补充训练未改善；记录第8条条件风险与任务成对指标，未部署。

同日[大规模配对来源审计](../results/bipia/large_pair_source_audit_v1/report_ZH.md)完成：SecFid/ASPI固定快照已核验，尚未训练；SecOPD是后续训练候选，需先确认研究使用条件。审计展开行数不计作获准训练样本。

S6 原型已经整理为两个可独立运行、持续扩展和复用的 base：

1. [`prompt_injection`](prompt_injection/)：BIPIA 邮件及检索内容安全（P1 规则、P2 语义任务一致性、P3 工具权限、P3.1 显式授权；监督分类器为可选研究对照）。
2. [`data_poisoning`](data_poisoning/)：训练数据清单完整性与标签投毒检测（实蝇为默认数据，STL-10 对照，IP102 历史记录）。

每个文件夹都有自己的前端、后端、检测器、数据准备与评估程序、英文 README、中文 README，以及自己的 `start.cmd`。项目根目录的 `start.cmd` 是统一入口（http://127.0.0.1:8764/），只负责启动或复用两个后端，不实现检测逻辑。大型原始数据仍放在 `external`，生成数据放在 `data`，评估证据放在 `results`。

两个应用使用不同的本地端口，可以同时运行：

- 统一入口：`http://127.0.0.1:8764`
- 邮件提示注入：`http://127.0.0.1:8765`
- 图像数据投毒：`http://127.0.0.1:8766`

具体操作请进入对应目录阅读 `README_ZH.md`。

两个 baseline 的开发阶段、评估指标和完成标准见
[BASELINE_ROADMAP_ZH.md](BASELINE_ROADMAP_ZH.md)。
