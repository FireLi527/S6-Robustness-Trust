# 首轮多动作提取微调：方法与复现说明

日期：2026-10-01。本说明在运行期间整理；事前冻结依据是 `data/bipia/relation_sft_v1/protocol.json` 和运行目录中的代码、模型、数据哈希，不把本说明冒充事前注册文件。

## 目标与边界

任务是从用户任务或文档的一侧文本提取模式、多个动作、对象、引用性质、限制及缺失信息。两侧分别读取，当前输入不包含该条类别标签或期望字段。提取结果不授予工具权限。

这是首轮小规模LoRA可行性研究，不是大规模训练，也不是最终授权关系分类器。正常/风险/不确定类别作为人工语义记录保留，但不作为当前提取器的训练输出，因此不能从本轮字段匹配率推导攻击召回率、误报率或真实代理ASR。

## 数据来源及划分

- 原24条中文合成案例：人工已确认类别、任务范围、文档动作。保留原分组，只有12条训练种子进入本轮；其余12条未用于训练或本轮评估。
- 新18条中文合成案例：用户逐条确认类别与范围/动作，第13条动作描述补全。按预先固定的任务组划分为6训练、6验证、6测试。
- 合计18条训练案例（8个任务组）、6条验证（2组）、6条测试（2组）。每条含task/content两侧；相同训练侧别、文本、答案去重后26份训练记录。没有改写扩增来虚增样本量。
- 原第7条补充完整上传目的地，仍留在原保留组；原第10条的“不要告诉用户”纳入本轮训练答案的约束列表。两个批次的数字编号不同，使用old-/new-前缀防止混淆。
- 所有语义标签经用户确认；精确JSON枚举、原文证据跨度及技术拆分由助手转换并作出处校验，**不是用户逐字段审核过的机器真值**。原文证据存在不等于语义正确。
- 全部是同一助手编写的仓库风格合成文本，不是从真实仓库抽样。新评估组未用于梯度更新或少样本示例，但每集合只有两个任务组，不能作统计显著或广泛自然场景泛化结论。

## 训练参数

官方 `Qwen/Qwen3-4B`，固定HF版本 `1cfa9a7208912126459214e8b04321603b3df60c`，Apache-2.0。使用可训练的HF safetensors，不是直接训练Ollama GGUF。下载文件大小与SHA256已保存于 `external/qwen3_4b_train_v1/`。

独立WSL环境 `.venv-s6-qlora`，通过只读路径复用原`s6-training`的GPU PyTorch；新微调依赖安装在新环境，不改原图像训练环境。已验证NF4微型前反向传播。

- NF4四位基础模型，双重量化，BF16计算；冻结嵌入保持BF16控制显存。
- LoRA rank=8、alpha=16、dropout=0.05，只更新q_proj/v_proj的适配器参数；不更新基础权重。
- seed=2026；3个固定epoch；batch=1、梯度累积4；最后不足4条按实际条数平均。
- AdamW，学习率0.0002、weight_decay=0.01；梯度裁剪1.0，非重入梯度检查点。
- 只对答案与EOS计算损失，提示token全部mask为-100；2048 token训练上限，超限报错而不截断。实际最长555 token。
- 不用验证或测试选epoch、超参数或检查点；最终适配器为固定第三轮结束状态。

原始训练目录 `results/bipia/relation_sft_v1/` 完成了21个优化步并保存适配器，但随后生成阶段缺少BF16自动混合精度，报类型不匹配；该目录FAILED标记原样保留。

`evaluate_relation_sft_checkpoint_v1.py` 只读取已保存适配器，增加生成时的BF16 autocast，不重新训练。独立评估目录为 `results/bipia/relation_sft_v1_evaluation/`；其协议绑定原训练目录所有文件哈希，以防失败后换权重。

## 三组对照与指标

1. base_zero：相同NF4基础模型，关闭适配器，不给示例。
2. base_fewshot：关闭适配器，使用预先指定的三个训练案例old-9、old-16、new-4作为本侧示例。
3. adapter_zero：开启已训练适配器，不给示例。

三组均使用相同中文字段说明、greedy解码、最多1200个新增token、4096总预算，不强制JSON语法、不做输出修复或挑选重试。无EOS的长度耗尽输出判失败。实际提示与输入/输出token ID逐条保存。

每个集合6案例×2侧=12份输出，不能当作12个独立任务：同组重复任务文本使输出相关。

- valid：JSON契约与精确原文证据校验均通过；不是语义准确率。
- mode_correct：校验通过且模式与技术参考一致。
- actions_exact：校验通过且全部动作、种类、目标状态和候选字段严格一致。
- fields_exact：在以上基础上，限制与缺失信息也严格一致。忽略动作列表顺序和证据片段长度；目标数组顺序、操作措辞、限制拆分仍可能影响严格匹配。

严格字段匹配可能把语义可接受的不同粒度表达算错，需要在冻结评分后结合原文诊断；不能为了提高结果事后改参考答案。任务级冲突判断与安全执行边界尚未在本轮实现。

## 复现入口

所有命令从项目根目录运行。已有输出目录独占，重复运行会拒绝覆盖；不删除失败目录来重跑。

```powershell
wsl -d Ubuntu-24.04 -- .venv-s6-qlora/bin/python -m s6.prompt_injection.experiment_relation_sft_v1
wsl -d Ubuntu-24.04 -- .venv-s6-qlora/bin/python -m s6.prompt_injection.evaluate_relation_sft_checkpoint_v1
wsl -d Ubuntu-24.04 -- .venv-s6-qlora/bin/python -m s6.prompt_injection.verify_relation_sft_v1
& .\.venv-bipia\Scripts\python.exe -m s6.engineering.check
```

第一条保留原故障作为历史复现，不应作为新实验的推荐入口直接覆盖执行；新的训练重复应另建版本。

参考：[官方Qwen3-4B模型](https://huggingface.co/Qwen/Qwen3-4B)、[PEFT量化微调文档](https://huggingface.co/docs/peft/developer_guides/quantization)。未进行云端训练、模型上传、前端部署、Git提交或推送。
