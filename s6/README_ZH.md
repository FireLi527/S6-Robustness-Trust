# S6 两个独立安全 Base

S6 原型已经整理为两个可独立运行、持续扩展和复用的 base：

1. [`prompt_injection`](prompt_injection/)：BIPIA 邮件及检索内容安全。
2. [`data_poisoning`](data_poisoning/)：IP102 训练数据和清单完整性。

每个文件夹都有自己的前端、后端、检测器、数据准备与评估程序、英文 README、中文 README，以及自己的 `start.cmd` 启动入口——项目根目录不再保留公用启动器。大型原始数据仍放在 `external`，生成数据放在 `data`，评估证据放在 `results`。

两个应用使用不同的本地端口，可以同时运行：

- 邮件提示注入：`http://127.0.0.1:8765`
- IP102 数据投毒：`http://127.0.0.1:8766`

具体操作请进入对应目录阅读 `README_ZH.md`。

两个 baseline 的开发阶段、评估指标和完成标准见
[BASELINE_ROADMAP_ZH.md](BASELINE_ROADMAP_ZH.md)。
