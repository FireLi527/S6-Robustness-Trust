# 可信审批准备状态 v1

当前是独立于冻结检测器的离线开发候选。公开接口位于`approval_readiness_v1.py`，实验入口为`experiment_approval_readiness_v1.py`。

## 接口

`extract_readiness(task)`仅接收可信任务，返回schema、task_sha256、mode、requires_prior_approval、approval_availability、evidence和provenance。状态枚举为EXPLICITLY_MISSING、CONFLICTING或UNASSESSED，**没有根据文字声明生成已验证的权限或批准状态**。

`validate_readiness(task,state)`重新计算提取结果，拒绝状态篡改或旧任务绑定。`resolve_readiness(task,component,state=None)`保留原模型决策、原路由结果及risk_alert；若可信条件操作明确缺先前审批，准备决策为UNKNOWN并进入复核。任何结果均不授予执行权限。

有限双语模式明确标为规则提取，不代表模型学习或通用语义覆盖。引号和代码块遮蔽仅覆盖简单结构，复杂引号、转义、长距离指代和语用含义尚无完整解析。外部正文、模型理由、来源或标签不进入状态提取器。

## 冻结回归

```text
python -m s6.prompt_injection.experiment_approval_readiness_v1 --stage prepare
python -m s6.prompt_injection.experiment_approval_readiness_v1 --stage run
python -m s6.prompt_injection.experiment_approval_readiness_v1 --stage verify
```

从仓库根目录使用Windows的`.venv-bipia`。现有目录独占，禁止重复覆盖。577条源输入、既有模型输出、前版决策、来源核验和代码SHA固定；不重新调用模型或使用未知身份缓存。

门槛比允许少量下降更严格：每来源攻击命中不下降、正常误报不增加、正常自动不减少、原始风险信号不改变、RISK不转NORMAL、无执行授权、新32条UNKNOWN提高且风险与正常指标保留。门槛与数据在首次策略回放前冻结。

已通过回归及577条核验；工程521通过、2跳过，新增14项契约测试。两个新生产模块共188行，职责分开，保持旧冻结协议和首次失败结果。详见`results/bipia/approval_readiness_v1/report_ZH.md`。

本版基于已曝光数据设计，收益是状态层开发收益。独立确认、真实审批系统验证、拟调用参数溯源、前端默认接入均未实施。
