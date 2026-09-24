# 小组实蝇数据首轮实验

> 补充确认：用户已向同学确认文件名前9位为同一标本编号，当前分类训练/验证/测试集按标本隔离。下文未确认表述为运行时历史记录，由本条更新；冻结协议未改动。检测器内部交叉验证仍按图片分折。

5类，ZIP原图9244张，按推断文件名前9位编号分组。
类别取自压缩包名称，未独立核验。编号分组不等同于已确认的标本独立划分。
STL-10 基线与结果保留；本实验单独存储。

## 分类模型

| 条件 | 训练图片 | 验证图片 | 测试图片 | 测试准确率 | Macro-F1 |
|---|---:|---:|---:|---:|---:|
| clean_subset | 6531 | 1392 | 1321 | 99.24% | 0.9914 |

## 固定语义检测器迁移

| 条件 | 投毒数 | 检出精确率 | 投毒召回率 | 干净误报率 |
|---|---:|---:|---:|---:|
| clean_subset | 0 | None | None | 4.38% |
| label_flip_05 | 327 | 0.5277 | 0.9327 | 4.40% |
| label_flip_10 | 653 | 0.6827 | 0.9357 | 4.83% |
| targeted_0_to_1 | 188 | 0.1991 | 0.4894 | 5.83% |

## 限制

Thresholds unchanged from prior experiments; no tuning on fruit-fly results.
Candidate train images only; held-out classification val/test images not used by detector.
Detector OOF folds use individual images, not specimen groups; related views may share folds.
Filename grouping is an unverified identity proxy; exact duplicates excluded but near duplicates may remain.

检测结果只使用候选训练图片；测试标签不用于调阈值。检测器内部按图片交叉验证，同组视角之间仍可能相关。
本轮默认只训练干净分类模型，没有完成该数据集的防御后重训练或多种子验证。
组间独立性需要同学确认命名规则后进一步核验；不能仅凭本轮高准确率宣称真实部署泛化。

核验通过：全部9244张图片字节、分组隔离、模型检查点、1392条验证与1321条测试预测、四组投毒检测计数。详见 verification.json。
