# STL-10 Image Label-Poisoning Baseline

The active dataset is STL-10 as of 2026-09-11. See [current setup and protocol](README_ZH.md). Historical IP102 results remain under `results/ip102_poisoning/`; [old documentation](README_IP102_HISTORY.md) describes that retired configuration, not the active detector.

Run from the project root using the existing Python environment:

```text
python -m pip install -r s6/data_poisoning/requirements-data.txt
python s6/data_poisoning/download_stl10.py
python s6/data_poisoning/prepare_stl10_poisoning.py
python s6/data_poisoning/evaluate_manifests.py
python s6/data_poisoning/evaluate_semantic.py
python s6/data_poisoning/app.py
```

The download uses a pinned public mirror and verifies both Parquet SHA-256 and reconstructed official image/label binary MD5 checksums. Unlabeled images are not needed.

Custom S6 protocol: 4,000 candidate training images, 1,000 validation images stratified from official training data, and all 8,000 official test images. All ten classes are used. Four conditions: clean, 5% random flip, 10% random flip, and 20% of airplane labels flipped to bird (2% of all training samples). This is not the official STL-10 fold benchmark.

Detector v0.5.0 uses raw frozen CLIP features without NCA. Independent fold projections cannot safely be concatenated for global distance calculations. We retain the original weights and thresholds without tuning on STL-10 attacks. Scores are not calibrated poisoning probabilities. Candidate-label contamination and pretrained-data overlap remain limitations.

The detector never reads hidden scoring truth. Cached evaluation results bind both detector and manifest hashes. Use `train_stl10_models.py` for ten-class ResNet18 experiments; `train_ip102_models.py` remains the historical IP102 trainer. No old IP102 accuracy should be reported as an STL-10 measurement.

Local UI: http://127.0.0.1:8766, or use `start.cmd` after downloading the data.

## First downstream training completed (2026-09-18)

Four ResNet18 runs completed with seed 2026 and 20 epochs, selected by validation macro-F1. Test accuracy: clean 94.44%, 5% flip 92.49%, 10% flip 89.89%, targeted 93.03%. Airplane-to-bird test error rose from 0.375% to 10% under targeted poisoning. Checkpoints, hashes, and all test prediction metrics were verified. This is a single-seed attack baseline; defense retraining and multi-seed replication remain next steps. See [report](../../results/stl10_poisoning/model_training/training_report_ZH.md).

## Defense validation completed (2026-09-19)

Eight additional models compare fixed ALLOW-only screening with equal-count random removal. Screening accuracy for clean/5%/10%/targeted conditions: 93.95%/92.81%/93.79%/94.08%. Targeted airplane-to-bird error falls from 10% to 0.125% versus 8.875% with random removal. All 12 models and per-sample metrics verified. Single-seed evidence only; multi-seed replication remains outstanding. See [defense report](../../results/stl10_poisoning/defense_training/defense_report_ZH.md).


### 本地控制台默认数据源

启动 `start.cmd` 后访问 http://127.0.0.1:8766/。页面和未指定 corpus 的 API 默认使用同学实蝇数据，读取 `grouped_defense_v1` 已冻结的检测与 12 组训练对照；页面顶部可切换 STL-10 历史对照。实蝇为 seed 2026 单种子，STL-10 为三种子均值及样本标准差。离线训练脚本的 `dataset_config.py` 保持原有 STL-10 配置。

实蝇结果展示前核验协议、检测器、预测和清单哈希关联；不匹配时报告错误，不自动使用旧检测器重算。样本检查器优先展示改标样本，仅用于演示。训练表的 0 → 1 错误率与总体准确率需同时解读。
