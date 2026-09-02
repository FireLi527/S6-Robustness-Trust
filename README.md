# S6 Robustness & Trust

This repository contains two research baselines for studying security risks around
LLM applications and model training.

| Baseline | Dataset | Main checks | Local app |
| --- | --- | --- | --- |
| Prompt injection defense | BIPIA EmailQA | P1 rule detection, P2 semantic task consistency, and P3 tool policy | `http://127.0.0.1:8765` |
| Training-data poisoning detection | IP102 | Manifest integrity, semantic label consistency, and controlled poisoned-model training | `http://127.0.0.1:8766` |

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
- [Milestone roadmap](s6/BASELINE_ROADMAP.md)

## Dataset references

- Xiaoping Wu, Chi Zhan, Yu-Kun Lai, Ming-Ming Cheng, and Jufeng Yang. “IP102: A
  Large-Scale Benchmark Dataset for Insect Pest Recognition.” CVPR, 2019.
- Jingwei Yi, Yueqi Xie, Bin Zhu, Keegan Hines, Emre Kiciman, Guangzhong Sun, Xing
  Xie, and Fangzhao Wu. “Benchmarking and Defending Against Indirect Prompt
  Injection Attacks on Large Language Models.” arXiv:2312.14197, 2023.
