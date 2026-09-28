# 仓库内容注入数据盘点：暂不重训

本轮新增第三个公开来源，并核对已有两个来源的独立样本数、信任边界和历史使用情况。审计脚本只读取数据，保存来源哈希与统计；没有复制攻击正文进 Git、没有重训、没有更改检测或授权流程。

| 来源 | 表面行数 | 有效信息与当前用途 |
|---|---:|---|
| [RepoGuardBench](https://github.com/DaoyuanLi2816/RepoGuardBench) 代码注释 | 470 攻击组合、94 干净源码 | 94 个任务重复使用 5 种攻击目标/措辞；已用于开发，不是独立测试。数据许可 [CC BY 4.0](https://github.com/DaoyuanLi2816/RepoGuardBench/blob/main/LICENSE-DATA)。 |
| [AgentInjectionBench](https://github.com/ppradyoth/AgentInjectionBench) `file_content` | 8 不安全、2 安全 | 混合 Python、README、JSON、JavaScript、笔记本；已用于确认，不能再次称为新测试。[Apache-2.0](https://github.com/ppradyoth/AgentInjectionBench/blob/main/LICENSE)。 |
| [prompt-injection-benchmark](https://github.com/AshwinNHacker/prompt-injection-benchmark) 非直接输入 | 13 注入、4 正常 | 新增的相邻领域候选，主要是工具输出/网页，不是仓库文件专属；另外 65 条直接用户输入因信任边界不同而排除。[MIT](https://github.com/AshwinNHacker/prompt-injection-benchmark/blob/main/LICENSE)。 |
| pandas/SciPy 原始 Python 代码 | 200 个文件 | 前两轮各 100 个、文件不重叠；只是按来源推定正常，未独立标注，不能替代合法维护指令难负例。 |

结论：**现在直接训练会高度依赖五种重复模板，且缺少未见仓库来源来验证提升。** `source_audit.json` 固定第三方文件哈希、数量及状态；`candidate_manifest.csv` 按 5 个模板家族、10 个已见外部案例、17 个新相邻领域案例列出 32 个候选单位，而不是把 470 行当成 470 个独立攻击。标注及切分约束见 `annotation_protocol_ZH.md`。

下一步数据工作是补充不同仓库来源的攻击文本与正常维护说明，并对用户任务、受控文本范围、偏离动作做双人标注；之后先冻结按仓库/家族隔离的测试集，才适合做轻量分类器训练。当前成果是可复核的数据准备与“不宜重训”判断，不是新的准确率提升。
