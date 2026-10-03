# data/bipia 目录索引

更新：2026-10-03。本文件只做导航，不移动、不合并、不修改任何数据。每个目录至少被一个脚本引用，很多还被协议文件按哈希绑定。目录如需移动，应作为独立任务：先改引用，再重新核验。

图例：
- **状态**：当前 = 正在使用；冻结 = 已完成的实验输入，仅用于复现；已取代 = 有更新版本，仅保留历史。
- **人工**：目录中有用户的人工审核记录，**丢失后无法重新生成**。
- **git**：是否已纳入版本库。40 个目录中只有 9 个已纳入。

## 1. 主 baseline（P1/P2、前端）

| 目录 | 状态 | 用途 | 主要使用者 | git |
| --- | --- | --- | --- | --- |
| `splits/` | 当前 | 冻结的开发/测试攻击类别划分 | `prepare_splits.py`、`evaluate_baseline.py`、`evaluate_semantic.py`、`app.py` | 是 |
| `generated/` | 当前 | BIPIA EmailQA 攻击样本（plain/stealth）及 Enron 干净邮件 | `prepare_bipia.py`、`eval_common.py`、`app.py` | 否（可由脚本重新生成） |
| `supervised/` | 冻结 | 监督分类 v1 的来源划分（前端实验对照） | `train_supervised.py`、`supervised_detector.py`、`app.py` | 是 |
| `supervised_v2/` | 冻结 | 监督分类 v2 协议 | `train_supervised_v2.py` | 是 |

## 2. 关系抽取主线（v3，当前研究）

依赖关系：`relation_scale_candidates_v1` → `relation_scale_training_v1` → `relation_scale_targets_v3` → `relation_scale_training_v3`；留出组为 `relation_holdout_v3_candidates` → `relation_holdout_v3`。

| 目录 | 状态 | 用途 | 生成脚本 | 人工 |
| --- | --- | --- | --- | --- |
| `relation_scale_candidates_v1/` | 冻结 | 34 组、204 条候选，以及四批语义审核 | `prepare_relation_scale_v1.py` | **是**（`human_review_01`–`04.json`） |
| `relation_scale_training_v1/` | 冻结 | v1 参考与 28/6 组划分，v1 训练和评估的输入 | `prepare_relation_scale_training_v1.py` | 否 |
| `relation_scale_targets_v3/` | 当前 | 按日志规则迁移得到的 v3 参考，含改动记录 | `prepare_relation_targets_v3.py` | 否 |
| `relation_scale_training_v3/` | 当前 | v3 训练数据和预先登记的评估方案 | `prepare_relation_scale_training_v3.py` | 否 |
| `relation_holdout_v3_candidates/` | 冻结 | 留出组候选与审核页 | `prepare_relation_holdout_v3.py` | **是**（`human_review.json`） |
| `relation_holdout_v3/` | 当前（密封） | 留出组 v3 参考，只评估一次 | `prepare_relation_holdout_v3_targets.py` | 否 |
| `relation_comparator_v1/` | 当前 | 比较器的登记与人工参考上的结果 | `register_relation_comparator_v1.py` | 否 |

## 3. 关系抽取早期版本（已取代，保留历史）

| 目录 | 状态 | 用途 | 人工 |
| --- | --- | --- | --- |
| `relation_development_review_v2/` | 冻结（被 v1 规模数据继承） | dev2 共 24 条的语义审核，规模扩充的种子 | **是**（`human_review.json`） |
| `relation_expansion_review_v1/` | 已取代 | 首轮扩充审核 | **是** |
| `relation_seed_conversion_v1/` | 已取代 | 首轮种子机器字段 | 否 |
| `relation_sft_v1/`、`relation_sft_v2/` | 已取代 | 首轮、第二轮 LoRA 训练数据 | 否 |
| `repository_scope_review_v1/` | 已取代 | 仓库风格材料的审核页与提案 | 审核页 |
| `repository_scope_human_review_v1/` | 已取代 | 上述材料的人工审核与字段确认 | **是** |
| `repository_scope_approved_v1/` | 已取代 | 审核通过后的字段 | 否 |

## 4. 授权关系与指令槽位实验（已完成，冻结）

| 目录 | 用途 |
| --- | --- |
| `authorization_probe_v1/` | NLI 授权关系探针（60 条已人工审核，记录在 results 侧） |
| `authorization_calibration_v1/` | 240 条程序合成材料，用于正则化与校准 |
| `authorization_relation_v1/` | 540 条配对关系训练材料 |
| `authorization_slots_v1/`、`authorization_slots_v1_design/` | 结构化授权槽位材料及其设计冻结 |
| `instruction_slots_v1/`、`instruction_slots_v1_design/` | 4B 槽位提取的首轮材料 |
| `instruction_slots_v2/`、`instruction_slots_v2_design/` | 少样本自由文本提取材料 |

## 5. 仓库/代码注入与跨来源实验（已完成，冻结）

| 目录 | 用途 | 人工 | git |
| --- | --- | --- | --- |
| `code_context_v1/`、`code_context_v2/` | 代码上下文注入样本 | 否 | 是 |
| `code_external_v1/`、`code_independent_v2/` | 外部或独立的代码注入评估集 | 否 | 是 |
| `maintainer_negatives_v1/` | 维护者文档难负例 | 否 | 是 |
| `repo_file_v1/` | 仓库文件划分 | 否 | 否 |
| `repo_file_v2/` | 仓库数据扩充候选与多轮审核 | **是** | 否 |
| `repo_file_review_v1/` | 仓库文件标注审核 | **是** | 否 |
| `native_pairs_v1/` | 原生配对数据（含 Apache-2.0 许可） | 否 | 否 |
| `prerequisite_review_v1/` | 前置条件分组审核 | **是** | 否 |
| `cross_source_v1/` | 跨来源训练与评估数据 | 否 | 否 |
| `secopd_pairs_v1/` | SecOPD 配对 | 否 | 否 |

## 6. 需要特别保护的目录

以下目录含有用户的人工审核记录，且**都没有纳入 git**，建议优先提交或另行备份（提交需用户确认）：

`relation_scale_candidates_v1`、`relation_holdout_v3_candidates`、`relation_development_review_v2`、`relation_expansion_review_v1`、`repository_scope_human_review_v1`、`repo_file_v2`、`repo_file_review_v1`、`prerequisite_review_v1`。

`data/` 下其余目录（`fruitfly_poisoning`、`diptera_poisoning`、`stl10_poisoning`、`ip102_poisoning`）属于图像数据安全 baseline，不在本索引范围内。
