# 邮件提示注入 Base

这个 base 演示 S6 安全层如何在邮件、网页或检索文本进入 Orchestrator、语言模型或高权限工具之前进行检查。它包含 BIPIA 数据构造、可解释的规则检测器、批量评估，以及与 Python 后端真实连接的本地前端。

## 目录结构

```text
prompt_injection/
├─ app.py                    本地 HTTP 后端
├─ detector.py               P1 规则引擎：ALLOW / REVIEW / BLOCK 判定策略
├─ semantic_detector.py      P2 语义任务一致性检测器
├─ prepare_bipia.py          构造 BIPIA 攻击样本
├─ prepare_splits.py         固定开发组和类别不重叠的测试组
├─ tool_policy.py            P3 工具调用策略：ALLOW / HUMAN_REVIEW / DENY 门控
├─ confused_deputy_scenarios.py  人工编写的 P3 演示/评估用例集
├─ eval_common.py            评估脚本共用的数据加载和指标工具函数
├─ evaluate_baseline.py      P1 分组评估、延迟和失败案例输出
├─ evaluate_semantic.py      P2 规则/语义/混合三系统对比
├─ evaluate_tool_policy.py   P3 危害遏制效果评估
├─ requirements-windows.txt  Windows 数据处理依赖
├─ start.cmd                 当前 base 的双击启动入口
├─ tests/                    独立单元测试和 HTTP 集成测试
└─ web/
   └─ index.html             浏览器前端
```

大型数据和生成结果放在代码目录之外：

```text
external/BIPIA/                    微软原始仓库
external/minilm_cache/             缓存的 MiniLM 句向量模型权重（P2）
data/bipia/generated/              生成的 JSONL 样本
data/bipia/splits/                 固定攻击划分清单
data/bipia/semantic_embedding_cache.npz  缓存的逐条文本 MiniLM 向量（P2）
results/bipia/                     评估 CSV 和 JSON
```

## 快速启动前端和后端

双击本目录下的 `start.cmd`，或在终端中直接运行它。

后端会运行在：

```text
http://127.0.0.1:8765
```

浏览器会自动打开前端。使用过程中不要关闭终端；需要停止时，在终端按 `Ctrl+C`。

### 前端如何使用

1. 页面顶部查看检测器版本、配置指纹、固定划分和 plain/stealth P1 指标。
2. 选择开发组或测试组，以及 plain 或 stealth 攻击形式。
3. 点击“随机载入 BIPIA 样本”，再运行安全检测。
4. 查看 `ALLOW / REVIEW / BLOCK`、风险分数、判定原因和高亮风险语句。
5. 也可以粘贴自己的邮件、网页、用户输入或检索内容。

`ALLOW` 只表示当前 baseline 没有命中已配置的风险信号，不代表绝对安全。
`REVIEW` 表示需要第二层检测器或人工复核。`BLOCK` 表示内容不应影响模型指令或触发高权限动作。

## 手动启动后端

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\app.py'
```

可选参数：

```text
--port 8765       修改本地端口
--no-browser      只启动后端，不自动打开浏览器
```

### 后端接口

#### `GET /api/status`

返回当前检测器版本、配置哈希、阈值、固定划分规模和最近一次 P1 评估摘要。

#### `GET /api/example`

随机返回一封生成的 BIPIA 攻击邮件、攻击类别和插入位置。支持查询参数，例如：

```text
/api/example?split=development&encoding=stealth
```

#### `GET /api/tool-scenario`

随机返回 P3 混淆代理（confused-deputy）用例集中的一条：`scenario_id`、`description`、
`content`、`tool_name`、`target`、`parameters`，以及一个 `ground_truth` 对象
（`triggered_by_untrusted_content`、`actually_harmful`）。真值标签仅用于演示教学——
这是一个小型示例用例集，不是对访客输入的盲评估。

#### `POST /api/detect`

请求（`tool_name`/`target` 可选；留空或省略则跳过 P3 检查）：

```json
{"text": "需要检查的不可信邮件或检索内容", "tool_name": "send_email", "target": "user@company.example"}
```

响应：

```json
{
  "decision": "BLOCK",
  "score": 6,
  "reasons": ["instruction-override language"],
  "detector": "s6-rule-prompt-injection",
  "version": "0.2.0",
  "config_hash": "...",
  "highlights": [
    {"start": 20, "end": 48, "label": "instruction override"}
  ],
  "tool_policy": {
    "detector": {"detector": "s6-tool-call-policy", "version": "0.1.0", "config_hash": "..."},
    "decision": "DENY",
    "reasons": ["high-impact action blocked: content detector flagged BLOCK"],
    "permission": "EXTERNAL_COMMUNICATION"
  }
}
```

Orchestrator 可以调用这个接口，也可以直接从 `detector.py` 导入
`detect_prompt_injection`。安全判定全部由后端完成，前端只负责展示。每一次带
`tool_name` 的真实请求还会向 `results/bipia/tool_policy_audit.jsonl` 追加一条
不含真值标签的审计记录。

## 构造和评估 BIPIA

先创建固定的攻击划分。开发组使用 BIPIA train 类别，但排除与 test
重叠的 `Language Translation`；测试组使用全部 BIPIA test 类别，因此两组类别严格不重叠：

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\prepare_splits.py'
```

然后分别生成 EmailQA train/test 攻击样本：

```powershell
$python = 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe'
$prepare = 'E:\研究生\高级计算机项目\s6\prompt_injection\prepare_bipia.py'
& $python $prepare --task email --split train
& $python $prepare --task email --split test
```

评估干净邮件和攻击邮件：

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\evaluate_baseline.py'
```

评估会生成：

- `email_p1_plain_summary.json`：开发组和测试组的完整分组指标、数据哈希、检测器版本和配置哈希。
- `email_p1_plain_decisions.csv`：每条样本的判定、原因与延迟。
- `email_p1_plain_failures.csv`：漏检攻击和干净误报。

当前规则 v0.2.0 的 plain 结果为：开发组10,500条攻击，检出率65.71%、干净误报率0%；测试组11,250条攻击，检出率93.47%、干净误报率2%。加入 `--stealth` 生成并评估 Base64 版本后，两组检出率分别为98.57%和96.08%。这些数字应和 JSON 中的延迟及分组结果一起报告。

运行自动化测试：

```powershell
Set-Location 'E:\研究生\高级计算机项目\s6\prompt_injection'
& '..\..\.venv-bipia\Scripts\python.exe' -B -m unittest discover -s tests -v
```

仓库现成可用的任务还包括 `table` 和 `code`。网页问答和摘要数据由于原始许可证限制，需要另外取得来源数据。

## P2：语义任务一致性检测器

P1 规则引擎只在某一行"句法上"看起来像指令时才会命中（要求以祈使动词开头）。这正是
Anagramming、Misspelling Intentionally、Space Removal & Grouping 这类混淆攻击类别能够
绕过它的原因：打乱顺序或拼写混淆会破坏正则匹配，却不会破坏指令本身的效果。

`semantic_detector.py` 增加了一个独立信号，问的是另一个问题：这条疑似指令的内容，
真的和用户提出的任务相关吗？它用 `sentence-transformers/all-MiniLM-L6-v2`
（通过原生 `transformers` 加载，不需要额外安装 `sentence-transformers` 包）分别编码
用户的真实任务（BIPIA 的 `question` 字段）和邮件内容中每一行足够长、非表头格式的候选
行，然后如果*最不相关*的那条候选行相似度低于阈值就发出警告。它从不读取 BIPIA 的
攻击标签——唯一输入是 `question` 和 `context`，这两项在真实部署中本来就存在。

运行三系统（纯规则 / 纯语义 / 混合）对比评估：

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\evaluate_semantic.py'
```

第一次运行会下载约 90MB 的 MiniLM 模型并缓存到 `external/minilm_cache/`，同时为开发组
和未见测试组中每条不重复的用户任务/候选行字符串计算向量（一共几百条不重复字符串，
CPU 上耗时几秒），结果缓存到 `data/bipia/semantic_embedding_cache.npz` 供后续复用。
加 `--stealth` 可评估 Base64 编码版本，与 `evaluate_baseline.py` 保持一致。

实测结果（plain / stealth 编码，开发组 / 未见测试组）：

| 数据集切分 | 编码方式 | 系统 | 攻击检出率 | 干净误报率 |
|---|---|---|---|---|
| development | plain | rule / semantic / hybrid | 65.71% / 43.66% / 79.78% | 0% / 4% / 4% |
| unseen_test | plain | rule / semantic / hybrid | 93.47% / 37.05% / 97.08% | 2% / 4% / 4% |
| development | stealth | rule / semantic / hybrid | 98.57% / 14.05% / 98.65% | 0% / 4% / 4% |
| unseen_test | stealth | rule / semantic / hybrid | 96.08% / 17.96% / 96.21% | 2% / 4% / 4% |

混合系统（取规则和语义中更严重的判定）在每一种切分和编码组合上都比纯规则系统召回率
更高，但代价一致：干净误报率从 0-2% 升到 4%（每个切分 50 封干净邮件中多 1 封）。
在明文攻击上召回率提升最大，因为语义信号独立找回了规则引擎完全漏检的样本，且集中在
路线图中指出的规则盲区类别（Information Retrieval、Content Creation、Misspelling
Intentionally、Learning and Tutoring、Clickbait）。在 stealth 攻击上，规则引擎的
`encoded_instruction` 信号已经能抓住绝大多数攻击，纯语义信号的增益有限。完整说明见
`s6/BASELINE_ROADMAP.md` 的 P2 里程碑，包括为什么 4% 的干净误报率（50 封中的 2 封）
在这个样本量下置信区间很宽。

`semantic_detector.py` 中的 `REVIEW_SIMILARITY`/`BLOCK_SIMILARITY` 仅根据开发组数据
校准，遵循与 P1 规则调整相同的实验完整性规则：未见测试集的结果不能用于反过来调整阈值。

P2 已经接入 `app.py`/`web/index.html`：在内容旁边填写 `question`（真实任务）即可
实时触发语义检测和混合判定，此外仍可用上面的独立评估脚本。

## P3：动作与权限遏制

P1 和 P2 回答的是同一个问题——*这段内容是不是注入攻击？*——两者都可能漏检。路线图的
下一个问题不同：*如果注入被漏检，最小权限能否阻止它造成真实危害？* `tool_policy.py`
独立于两个内容检测器回答这个问题：只根据内容判定结果（`ALLOW`/`REVIEW`/`BLOCK`）和
请求的工具调用（`tool_name`、`target`），对高影响动作（`WRITE`、
`EXTERNAL_COMMUNICATION`、`SENSITIVE_DATA`）按照预先批准的可信目标清单进行门控，
返回 `ALLOW` / `HUMAN_REVIEW` / `DENY`。只读动作（`read_email`、`search_documents`）
不受此层限制——内容判定是 P1/P2 的职责，不是这一层的。它从不读取真值标签：
`ToolCall` 在结构上就没有危害相关字段，`evaluate_tool_call` 的双参数签名由单元测试
校验，防止未来悄悄加入真值输入。

`confused_deputy_scenarios.py` 是一个小型的人工编写用例集（18 条，不是
`prepare_*.py` 生成的语料），覆盖全部四个权限层级：面向可信/不可信目标的正常请求、
P1 能正确拦截的攻击，以及最核心的演示——P1 漏检（判为 `ALLOW`）但目标是不可信目的地
的攻击，这一层仍会把它们路由到 `HUMAN_REVIEW` 而不是放行执行。

运行评估：

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\evaluate_tool_policy.py'
```

实测结果（全部 18 条用例，均参与评估——原因见下方"不做数据切分"说明）：

| 指标 | 数值 |
|---|---|
| 判定分布（ALLOW / HUMAN_REVIEW / DENY） | 5 / 9 / 4 |
| 没有这一层时，危害用例的动作成功率 | 100.00%（按构造必然如此） |
| 有这一层时，危害用例的动作成功率 | 11.11% |
| 内容检测器漏检、但这一层成功遏制 | 9 条危害用例中的 3 条 |
| 良性高影响请求的额外摩擦率 | 71.43% |

最小权限把危害动作成功率从 100% 降到 11.11%，但有真实代价：大多数面向尚未获信任
目标的良性高影响请求也会被转入人工复核。这个代价被如实报告而非隐藏，符合本项目一贯
的做法——收益指标必须搭配摩擦成本一起呈现。

与 P1/P2 不同，这里不做开发/测试划分。那个划分的目的是保护一个*可调的数值阈值*
（`REVIEW_THRESHOLD`/`BLOCK_THRESHOLD`、`REVIEW_SIMILARITY`/`BLOCK_SIMILARITY`）不被
拿来在打分的同一批数据上过拟合。`tool_policy.py` 没有可调阈值——它的判定表由路线图
的四个权限类别和一份预批准目标清单固定下来，并非从这份用例集中校准得到——因此每条
用例都参与评估，用例集与真实检测器结果的一致性改由单元测试校验。

**已知的遏制缺口**（用例集中专门有一条场景把它演示出来，而不是只在文档里描述）：
如果一次注入既绕过了内容检测器（判为 `ALLOW`），又把动作指向一个已经被预先批准的
可信目标，这一层同样会返回 `ALLOW`。最小权限能缩小漏检注入的影响半径，但不能完全
消除它。

P3 已经接入 `app.py`/`web/index.html`：在内容旁边选择工具和目标（或点击"加载
混淆代理场景"）即可与 P1/P2 一起实时运行这项检查。

## 安全与研究限制

- 当前检测器是可解释的硬编码 baseline。
- 同义改写、混淆和新攻击可能绕过关键词规则。
- v0.2.0 开发前已经看过旧 BIPIA test 汇总结果，因此新清单只对未来版本构成固定的前瞻测试协议，不能把 v0.2.0 描述为完全未见的盲测。
- 当前干净邮件只有 train/test 各50封，仍需引入独立且规模更大的干净语料。
- 数据集上的结果不能直接等同于真实系统安全水平。
- P3 的最小权限门控能缩小漏检注入的影响半径，但不能完全消除：既绕过 P1/P2、又指向
  已被信任目标的注入不会被这一层拦下（见上文"已知的遏制缺口"）。实际部署仍可受益于
  本原型未实现的独立工具授权、数据来源记录、监控和回滚机制。
- 服务只绑定 `127.0.0.1`，粘贴内容不会上传到外部。

英文说明见 [README.md](README.md)。

后续里程碑见 [../BASELINE_ROADMAP_ZH.md](../BASELINE_ROADMAP_ZH.md)。
