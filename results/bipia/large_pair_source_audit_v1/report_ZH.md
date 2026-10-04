# 大规模任务配对来源审计

日期：2026-09-30，Australia/Sydney。状态：本轮来源审计和工程测试完成，尚未开展新模型训练。没有将评估探针自动标为越权攻击，也没有给无任务正文补造用户任务。

## 结论

找到可下载的千条级配对材料，但不能仅因达到数量就按原任务边界标签训练。当前最贴近训练需求的后续候选是SecOPD；需先确认其研究使用条款与数据映射。当前已下载的SecFid、ASPI均保持审计用途。

|来源|核实结果|本轮处理|
|---|---|---|
|SecFid主集|1,168条有原始instruction、base与input；主要评价执行/处理/忽略探针的行为，不是现成的正常/越权二分类标签|固定版本下载，保留原字段；风险标签空，不训练|
|SecFid工具场景|252条有任务、干净和含探针工具响应，但仅7种任务；来自InjecAgent相关协议|固定版本下载、分组审计；不能冒充252种独立任务|
|ASPI|728场景，带原任务、歧义任务、澄清问题及正常/对抗回答；数据卡将训练列为范围之外|固定版本下载，仅审计；不把澄清通道伪装成低信任工具输出|
|InjecAgent|公开说明1,054组合案例来自17种用户工具任务和攻击组合；主要为攻击评估|记录为评估方向，不重复下载凑训练量|
|Agentic Boundary Pairs|字段为text及pair/scenario标签，没有单独原始用户任务字段|排除本轮联合训练候选|
|SecOPD训练集|公开卡列19,155条，保留原始数据与精确注入片段；明确用于防御训练研究，但没有独立数据集许可证声明|只审计公开卡和文件元数据；未下载192MB训练正文|
|Agent-IPI Structured Interaction|有instruction/input等字段，但当前卡/文件清单未提供明确许可证信息|只核实元数据，不纳入训练|

以上不是对数据质量的全面认证或法律结论。尤其公开可读不等于本轮已经核实了所有使用/再分发条件。

## 已下载材料的实际规模

|材料|展开行数|不同任务-上下文-正文组合|不同任务文本|审计连通组|最大组行数|
|---|---:|---:|---:|---:|---:|
|SecFid主集|2,336|2,334|789|788|218|
|SecFid工具场景|504|259|7|7|72|
|ASPI|2,912|2,742|147个歧义任务文本|59|676|

ASPI原始任务只有92个（suite＋user_task_id），147是歧义改写文本的数量，不是147个独立原始任务。正常澄清的不同任务/问题/回答组合558个，不能把重复正常回答当作728个独立负例。

连通组规则：共享原始配对、同规范化任务、同正文、同ASPI原始任务ID，以及字符3–5元TF-IDF余弦≥0.88的正文关联取连通分量。最大特征数50,000，块大小64。这里只标注审计组，未分配训练/验证/测试。该规则不能排除全部语义改写，未开展与所有历史语料的全量近重复检查，因此不声称已消除历史污染。

## 为什么不直接训练

SecFid主集的probe.type有890条knowledge、278条command。第一条要求统计医疗专科名称，插入内容是询问皮肤科对应器官的知识问句：回答它、把其中实体计入统计、忽略它是不同模型行为；“插入过一个问句”不等同于已确认存在恶意越权。若将base一律标正常、input一律标攻击，可能学到探针存在性，而不是上一轮的用户授权边界。

工具场景虽有明显注入内容，上游仍关注既不执行其中指令、又保留任务所需内容的安全性和忠实度；简单删除所有风险文本并不等同于完成其原始评估目标。

ASPI的CP变体确实覆盖将攻击目标伪装成前置条件，方向相关。但其主要输入是澄清回答，角色和任务状态是判定的一部分；将回答单独当仓库正文会改变威胁模型。按数据卡用途，先保留为可能的后续评估方向，不擅自拿来训练。

## 固定版本与文件

- SecFid：`mjhermon/SecFid@97fa8d11a98ad197e9a87770255171c6300bfbbf`，数据卡Apache-2.0，工具扩展含InjecAgent MIT归属说明。
- ASPI：`ScaleAI/aspi@8aaafd059a345eaf60019a6a35472c31a8527bd7`，卡列CC-BY-4.0，上游AgentDojo MIT。
- SecOPD元数据：`Sizhe-Chen/Qwen3.8-27B-Thinking-SecOPD-trainset@9ff5e25093995041997ea984c68a51f2b998d435`。
- Agent-IPI元数据：`Z-Edgar/Agent-IPI-Structured-Interaction-Datasets@351bab31fc77f8e8ec814e00b17487887ef8d4ad`。

下载目录：`external/paired_source_audit_v1/`。13份文件合计9,203,716字节；manifest记录原URL、字节数与SHA256。SecFid两份数据还与作者release_manifest校验值匹配。未执行上游脚本或数据中的指令，没有使用付费接口、登录凭据或提交外部消息。

本目录三个`*_audit_only.json`保持风险标签null、training_allowed=false、split=null。机器展开5752行只是审计材料总数，不是5752条获准训练样本。所有内容已被程序读取，首条还被人工式查看；不能称为封存未触碰测试集。

## 工程验收

新增5项契约测试，覆盖缺任务拒绝、无自动风险标签、澄清上下文保留、相同任务/正文不能跨组、重复ID拒绝。

统一检查：工程52、提示词151、图像31项通过，图像2项WSL相关跳过；共234项Python测试通过、2项跳过。提示词包装测试含11项Node逻辑测试。没有浏览器视觉验收。

13份下载哈希、审计导出状态/分组、38份既有受保护输入/代码均通过复核；未修改冻结结果、部署、提交或推送。

检查目录：`results/engineering/checks/20260929T145549Z-67a7265f/`。新增下载和审计模块分别负责固定快照与字段/分组验证，无训练路径；公共工程工具保持原样。

## 下一步需要确认什么

优先核实SecOPD：只提取可信任务、原始正文和注入正文做非商业课程防御研究，不使用chosen/rejected模型生成回答，不再分发数据。作者卡表示没有独立数据集许可，且列出上游Alpaca及其清洗版本条款差异；应由作者明确说明，或依据学校适用的数据使用规范确认，不能由本助手把不清晰的条款自行解释成已获许可。

可向作者询问（未发送）：

> We are conducting a non-commercial graduate-course project on defensive prompt-injection detection. May we use the trusted task, original input and injected input from this pinned release to train a classifier, excluding generated chosen/rejected completions and without redistributing the dataset? Which license and attribution requirements apply to these fields?

确认后再抽取1,000–3,000条规模的成组开发子集，检查任务/原始正文/注入模板重复，预先固定校准与评估边界。未确认之前不启动训练，不把上述其他来源的标签改写来绕过这个问题。

## 原始说明

- [SecFid数据卡](https://huggingface.co/datasets/mjhermon/SecFid)
- [ASPI数据卡及用途限制](https://huggingface.co/datasets/ScaleAI/aspi)
- [InjecAgent作者仓库](https://github.com/uiuc-kang-lab/InjecAgent)
- [Boundary Pairs数据卡](https://huggingface.co/datasets/3nesdeniz/agentic-prompt-injection-boundary-pairs)
- [SecOPD训练集与许可说明](https://huggingface.co/datasets/Sizhe-Chen/Qwen3.8-27B-Thinking-SecOPD-trainset)
- [Agent-IPI数据页](https://huggingface.co/datasets/Z-Edgar/Agent-IPI-Structured-Interaction-Datasets)
