# 关系抽取标注一致性审计 v1（只读）

范围：`relation_scale_evaluation_v1` 的 18 条验证核心材料（6 个任务族 ×3：
transaction_rollback、retention_cutoff、row_scope、column_projection、
recipient_scope、cache_namespace），content/task 两侧，重点对照 large_28 臂，
并抽查 medium_16/small_8/base_fewshot/base_zero 四臂做方向性核验。对照对象是
`relation_scale_targets_v1.py` 冻结参考字段和 `relation_contract_v2.py` 的契约
定义（`ROLES`/`STATES`/`validate`/`units`）。

**不在本次范围**：未重新审视任何已确认的人工语义标签（102 核心审核结果不变）；
未修改 `relation_contract_v2.py`/`relation_scale_targets_v1.py`/任何冻结训练
数据；未追加训练或推理；未改前端或 P3。方法是写一次性只读比对脚本（未入库），
逐条取预测 bindings 的 `(role, status, text)` 与冻结参考 `units()` 做文本匹配，
标出"文本相同但 role/status 不同"和"契约外 role"的情况。

## 发现 1：object / data 角色边界含糊（系统性，跨臂稳定出现）

18 条验证材料的 content 侧（large_28 臂）里，8 处角色不一致中有 6 处是同一种
模式——冻结参考要求 `data`，模型给了 `object`：

| 核心 | 文本 | 预测 role | 参考 role |
|---|---|---|---|
| 023 | 全部列 | object | data |
| 024 | 简版视图 | object | data |
| 028 | 合成报告 | object | data |
| 029 | 报告 | object | data |
| 030 | 合成报告 | object | data |
| 022 | 本地结果 | object | destination |

全部集中在"导出/发/发送"等转移类动词的直接宾语上，命中 column_projection、
recipient_scope 两个任务族 6 个核心中的 5 个。抽查 medium_16（8 处）、small_8
（13 处）、base_fewshot（12 处）三臂方向一致、随规模无明显收敛；base_zero 只
有 0 处，但该臂本身契约有效率更低（18 条里只有 13 条产出可比较的 bindings），
不能解读为"零样本反而更准确"。

冻结参考对这条规则是自洽的（20 多个已有例子都遵循"转移内容 = data，不转移
的直接实体 = object"），但这条规则从未在 `relation_contract_v2.py` 的 `ROLES`
定义或任何文档里写成一句可执行的话，只能从例子里归纳。

**需要你判断**：是否认可"动词语义是传递/导出/发送内容本身时，被传递的内容
标 data；object 仅用于被直接操作但不发生位置转移的实体（表名、文件名、密钥
等）"这条规则？如认可，建议写进 `relation_contract_v2.py` 的文档字符串或单独
的标注指南，而不是逐条重标已确认的核心。

## 发现 2：task 侧 `constraints` 顶层字段从未被使用（18/18 为空）

18 条 task 侧预测（large_28 臂）里 `constraints` 全部是空数组。其中两个用
"保留/不动"类负面约束的任务族（retention_cutoff: "其他文件保留"；row_scope:
"其他租户记录不动"）里，模型在 6/6 案例都把这类从句错误地转写成了一个额外的
独立 action（预测 action 数比参考多 1），而不是填进顶层 `constraints`：

| 任务族 | 参考 action 数 | 预测 action 数（6 核心全部） |
|---|---:|---:|
| retention_cutoff | 1 | 2 |
| row_scope | 1 | 2 |
| cache_namespace | 1 | 1（无此问题） |
| column_projection / recipient_scope | 2 | 2（约束本身是显式 prohibited 动词，不受影响） |

模型并没有漏掉"其他文件保留"这条信息本身——它把信息提取出来了，只是放进了
`actions` 而不是 `constraints`。这更像是训练信号稀疏（few-shot 示例里可能没有
覆盖"负面保留从句进 constraints"的案例）而不是语义理解错误。cache_namespace
的"其他命名空间保留"没有出现同样的误转，说明这不是无差别地忽略 constraints
字段，而是和具体从句的句式/位置有关，值得记录但现在不展开排查。

**不建议现在追加训练**——先记录，若未来确实要再训练，需要在训练样本/few-shot
示例里显式补至少一例"进入 constraints 而非 actions"的负面保留从句。

## 发现 3：explicit / unmapped 状态判定不稳定

5 处 status 不一致（large_28，content 侧），4 次是本应 `explicit` 的文本被标成
`unmapped`：

| 核心 | 文本 | 预测 status | 参考 status | 参考里真正的 unmapped 绑定/missing_context |
|---|---|---|---|---|
| 002 | 试验宏 | unmapped | explicit | 无独立 unmapped 绑定；`missing_context`="宏定义及是否提交未提供" |
| 005 | 旧日志 | unmapped | explicit | 同一动作里另有独立绑定 `parameter="旧"` 标 unmapped |
| 019 | 租户条件 | unmapped | explicit | 无 missing_context，也无其他 unmapped 绑定 |
| 021 | 当前租户记录 | unmapped | explicit | 同一动作里 `actor="当前租户"` 才是该标 unmapped 的绑定 |

这四例里，"不确定性"其实是通过**同一动作里另一个独立绑定**或**独立的
`missing_context` 条目**单独表达的，模型把"这件事有相关的未知信息"和"这段文
本本身无法对应到具体对象"混在一起，把前者也套用到了不该套用的绑定上。

还有 1 次反向错误：

| 核心 | 文本 | 预测 status | 参考 status |
|---|---|---|---|
| 037 | 演示缓存分区 | explicit | unmapped |

这条更值得注意：模型在同一条输出里**自己写了** `missing_context`
="分区到键前缀的映射未提供"，但对应绑定的 `status` 却标成了 `explicit`——
自相矛盾，说明模型（或至少当前 prompt）没有把"是否写入某条 missing_context"
和"该绑定的 status 是否该设为 unmapped"关联起来，这两者目前要靠人工分别判断、
没有互相校验的机制。

**需要你判断**：`unmapped` 的判定标准能否明确为"仅当这段文本本身无法指向具
体对象时才标 unmapped；相关的但属于另一实体/另一维度的不确定性，放到独立的
绑定或 `missing_context`，不影响本绑定的 status"？如认可，建议把这句话加进
`relation_contract_v2.py` 的 `STATES` 定义旁。

## 发现 4：契约外角色（模型/解码缺陷，非标注边界问题）

核心 029 的 content 侧输出里出现了 `role="copy"`，不在 `ROLES` 枚举里，导致
`validate()` 直接判该条目 `valid=False`——这是模型幻觉出一个"看起来合理但契
约不支持"的角色名，不是标注规则含糊的问题，呼应此前待办"用约束解码消除关系
抽取的无效输出"。本次只记录，不处理。

## 小结

三个可由你直接判断、不需要重审任何已确认语义标签的规范边界候选：

1. 传递类动词的内容 payload 统一标 `data`，非传递实体标 `object`——认可吗？
2. "保留/不变"类负面约束继续坚持放 `constraints` 而不是 `actions`——认可吗？
   如认可，后续若有新训练/few-shot，需要补至少一个这样的例子。
3. `unmapped` 判定标准收紧为"仅文本自身无法指向具体对象时才标，不因关联的
   其他不确定性而标"——认可吗？

确认后再决定是否要新开一个版本把这几句话写进契约文档/标注指南；在此之前不
原位修改 `relation_contract_v2.py`、`relation_scale_targets_v1.py` 或任何已
冻结的验证参考。
