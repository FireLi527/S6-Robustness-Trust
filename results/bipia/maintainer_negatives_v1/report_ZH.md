# 正常维护说明候选：三仓库原始文档

从 [Requests](https://github.com/psf/requests)、[Flask](https://github.com/pallets/flask) 和 [pytest](https://github.com/pytest-dev/pytest) 的固定提交中，各抽取 10 条未修改的贡献、测试、安全或发布说明段落，共 30 条。选取只依据文档原文及维护/命令词汇，先于检测器评分冻结；每个源文件最多 4 条。原文仅留在本地忽略目录，版本控制保存文件哈希、行号与候选哈希。三个仓库分别按 Apache-2.0、BSD-3-Clause、MIT 许可；固定提交见 `protocol.json`。

P1 标记 3/30，实验性工作流信号标记 0/30。**这不是误报率**：30 条只是按来源推定正常的候选，其中有些是安全风险说明或代码块，尚未独立人工判定；关键词抽样也不代表真实仓库内容分布。`review_queue.csv` 将三条命中列为优先复核，并留出双人标注和裁定列。未复核样本不得作为可靠的 `benign` 标签训练或用于宣称独立测试效果。

另发现一套更贴近仓库文件的 [Prompt Injection Repository File Dataset](https://huggingface.co/datasets/prodnull/prompt-injection-repo-dataset)，卡片称有 5,671 条并包含正常难负例，但其文件访问要求登录并同意共享联系信息。用户表示愿意稍后自行完成授权；本轮没有绕过访问条件、下载该数据或引用其未见内容。授权后仍须审计来源、标签、重复家族、训练/测试划分及其已知域外误报问题，再决定是否训练。
