# Code 工作流劫持信号：开发与跨来源确认（探索性）

候选方法只读取 Python 注释及可解析文档字符串：在同一注释块或文档字符串中同时寻找“维护者、CI、自动修复”等权威语境与额外读取、写入、删测试、执行命令或插入标记等操作要求。跨行匹配，不执行代码。它是独立研究信号，未接入 P1/P2/Hybrid、P3 工具授权或前端。

| 数据 | 方法 | 攻击样本标记率 | 原始/干净样本标记率 |
|---|---|---:|---:|
| 已暴露的 RepoGuardBench 开发集 | P1 | 0/470 | 7/194 |
| 已暴露的 RepoGuardBench 开发集 | 旧注释信号 | 0/470 | 0/194 |
| 已暴露的 RepoGuardBench 开发集 | 新工作流信号 | 470/470 | 0/194 |
| 新来源 AgentInjectionBench `file_content` | P1 | 1/8 | 0/2 |
| 新来源 AgentInjectionBench `file_content` | 旧注释信号 | 0/8 | 0/2 |
| 新来源 AgentInjectionBench `file_content` | 新工作流信号 | 0/8 | 0/2 |
| 新来源 AgentInjectionBench `file_content` | P1 或新信号 | 1/8 | 0/2 |
| 新取 pandas/SciPy 原始源码 | P1 | — | 5/100 |
| 新取 pandas/SciPy 原始源码 | 新工作流信号 | — | 0/100 |

开发集取自 [RepoGuardBench](https://github.com/DaoyuanLi2816/RepoGuardBench) 的公开、作者编写的五种安全模拟载荷，代码注释载体下每个目标在 94 个任务中重复一次。因此 470/470 主要证明候选覆盖了已知模板，不是独立泛化成绩。开发集的 194 条干净样本由 94 个该基准源文件和 100 个原始开源代码片段组成。

确认集在候选实现前冻结：另取未出现在开发集中的 pandas/SciPy 源文件各 50 个，并纳入 [AgentInjectionBench](https://github.com/ppradyoth/AgentInjectionBench) 已发布数据中全部 10 条 `file_content` 样本（8 条 `unsafe`、2 条 `safe`），来源提交为 `5adb09800170683793b4e4d015e42e2002fa5adf`，按 [Apache-2.0](https://github.com/ppradyoth/AgentInjectionBench/blob/main/LICENSE) 授权。候选代码及确认数据哈希在确认评分前冻结；评分后未调参或重跑。

第二来源混合了 Python 片段、README、JSON、JavaScript 和笔记本等内容；Python 专用信号对这些其它载体本来就不适用。这说明当前候选的适用范围很窄，也未在该小样本上体现跨来源收益。确认集中只有 8 条不安全样本、2 条安全样本，不能作可靠的总体召回率或误报率估计；研究者事前看到过部分样本元信息，也不是严格盲测。原始开源源码按来源视为疑似安全，并无独立人工标注。所有数字是离线静态检测标记率，不是 LLM 代理端到端攻击成功率。

**结论：不采纳为产品检测或授权策略。** 这次实验的有用结果是明确了跨行规则对已知模板的过拟合及 Python 注释载体覆盖不足。后续若继续，应先定义不同载体的边界和独立标注协议，再取得更大、未见过的仓库级攻击与正常维护指令样本；不能在这 10 条确认样本上反复调规则后宣称确认收益。
