> 图像控制台默认使用 **同学五类实蝇数据集**；双翅目/实蝇科二分类为附加研究，STL-10 保留为历史对照。

# S6 Robustness & Trust

## 统一前端入口

双击根目录 **`start.cmd`**：自动启动所需的两个本地服务，并打开 **http://127.0.0.1:8764/**。默认进入同学实蝇图像实验，顶部切换提示词注入；两侧页面保留各自操作状态。已运行的模块会复用。

保持启动窗口运行；按 Ctrl+C 停止统一入口及由它启动的模块，原先已运行的模块不受影响。启动失败时查看 `results/local_frontend/` 日志。页面源码为 `index.html`，启动服务为 `frontend.py`。


This repository contains two research baselines for studying security risks around
LLM applications and model training.

| Baseline | Dataset | Main checks | Local app |
| --- | --- | --- | --- |
| Prompt injection defense | BIPIA EmailQA; independent Enron clean-email extension | P1 rules, P2 task consistency, P3 tool policy, P3.1 explicit approval | `http://127.0.0.1:8765` |
| Training-data poisoning detection | Five-class fruit flies (main); Diptera/Tephritidae additional study; STL-10 historical control | Manifest integrity, label consistency, and controlled poisoned-model training | `http://127.0.0.1:8766` |

## Project structure

```text
s6/
  prompt_injection/   Prompt-injection detector, evaluation, tests, and web console
  data_poisoning/     Data-poisoning detector, training, evaluation, tests, and web console
data/                 Small manifests and split definitions used by the experiments
results/              Reproducible summaries and compact evaluation artifacts
```

Large upstream datasets, generated BIPIA samples, embedding caches, virtual
environments, and model weights are intentionally excluded from Git. Follow the setup
instructions in each baseline before running the applications or reproducing the full
evaluation.

## Documentation

- [Project overview](s6/README.md)
- [中文项目概览](s6/README_ZH.md)
- [Prompt injection baseline](s6/prompt_injection/README.md)
- [提示词注入中文说明](s6/prompt_injection/README_ZH.md)
- [Data poisoning baseline](s6/data_poisoning/README.md)
- [数据投毒中文说明](s6/data_poisoning/README_ZH.md)
- [Milestone roadmap](s6/BASELINE_ROADMAP.md) · [里程碑规划](s6/BASELINE_ROADMAP_ZH.md)
- [S6 当前阶段中文汇总](results/s6_stage_update_20260928_ZH.md)
- [SecOPD 首轮配对训练：同来源提升与跨场景局限](results/bipia/secopd_training_v1/report_ZH.md)
- [跨来源训练：8组新模型、2组冻结对照及泛化评估](results/bipia/cross_source_training_v1/report_ZH.md)
- [授权关系联合读取：NLI小规模方法验证](results/bipia/authorization_probe_v1/report_ZH.md)

## Dataset references

- Xiaoping Wu, Chi Zhan, Yu-Kun Lai, Ming-Ming Cheng, and Jufeng Yang. “IP102: A
  Large-Scale Benchmark Dataset for Insect Pest Recognition.” CVPR, 2019.
- Jingwei Yi, Yueqi Xie, Bin Zhu, Keegan Hines, Emre Kiciman, Guangzhong Sun, Xing
  Xie, and Fangzhao Wu. “Benchmarking and Defending Against Indirect Prompt
  Injection Attacks on Large Language Models.” arXiv:2312.14197, 2023.
