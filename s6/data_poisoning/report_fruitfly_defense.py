"""Recompute held-out metrics and report all twelve fixed fruit-fly conditions."""
import csv
import numpy as np
from pathlib import Path
from sklearn.metrics import accuracy_score,f1_score,confusion_matrix
from prepare_fruitfly import DATA,IMAGES,RESULTS,sha,write_json
from prepare_fruitfly_grouped_defense import DEST,OUT,read,NAMES
from train_fruitfly_defense import verify_run,require
from manifest_protocol import load_candidate_manifest,load_hidden_ground_truth,validate_candidate_truth_pair


def csv_rows(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def validate_predictions(s):
    history=csv_rows(Path(s['result_dir'])/'history.csv')
    require(len(history)==20,'Incomplete training history')
    for split,key in (('val','validation'),('test','test')):
        predictions=csv_rows(Path(s['result_dir'])/f'{split}_predictions.csv')
        expected={}
        for line in (IMAGES/f'{split}.txt').read_text().splitlines():
            filename,label=line.rsplit(maxsplit=1)
            expected[f'classification/{split}/{label}/{filename}']=int(label)
        require(len(predictions)==len(expected),'Missing held-out predictions')
        require({r['sample_id']:int(r['true_label']) for r in predictions}==expected,'Held-out IDs/labels changed')
        y=[int(r['true_label']) for r in predictions];p=[int(r['predicted_label']) for r in predictions]
        require(abs(accuracy_score(y,p)-s[key]['accuracy'])<1e-6,'Accuracy mismatch')
        require(abs(f1_score(y,p,average='macro')-s[key]['macro_f1'])<1e-6,'F1 mismatch')
        require(confusion_matrix(y,p).tolist()==s[key]['confusion_matrix'],'Confusion matrix mismatch')
        rate=sum(a==0 and b==1 for a,b in zip(y,p))/sum(a==0 for a in y)
        require(abs(rate-s[key]['targeted_0_to_1_rate'])<1e-6,'Targeted error mismatch')


def main():
    progress=read(OUT/'training_progress.json');plan=read(DEST/'selection_plan.json')
    require(progress['completed_runs']==progress['expected_runs']==12,'Experiments not complete')
    require(progress['selection_plan_sha256']==sha(DEST/'selection_plan.json'),'Selection changed')
    runs={s['dataset']:s for s in progress['summaries']}
    require(set(runs)==set(NAMES)|set(plan['variants']),'Duplicate or missing condition')
    base=runs['clean_subset'];rows=[]
    for name,s in runs.items():
        manifest=DATA/'manifests'/f'{name}.csv' if name in NAMES else DEST/'manifests'/f'{name}.csv'
        verify_run(s,base,manifest,len(load_candidate_manifest(manifest)))
        validate_predictions(s)
        if 'checkpoint_sha256' in s:require(sha(Path(s['checkpoint']))==s['checkpoint_sha256'],'Checkpoint changed')
    for source in NAMES:
        original=load_candidate_manifest(DATA/'manifests'/f'{source}.csv')
        truth=validate_candidate_truth_pair(original,load_hidden_ground_truth(DATA/'hidden_ground_truth'/f'{source}.csv'))
        poisoned={sid for sid,r in truth.items() if r['poisoned']=='true'}
        for strategy in ('untreated','random','semantic'):
            name=source if strategy=='untreated' else f'{source}__{strategy}'
            s=runs[name];removed=set() if strategy=='untreated' else set(plan['variants'][name]['removed_sample_ids'])
            if strategy!='untreated':
                kept=load_candidate_manifest(DEST/'manifests'/f'{name}.csv')
                source_map={r['sample_id']:r for r in original}
                require({r['sample_id'] for r in kept}==set(source_map)-removed,'Selection membership changed')
                require(all(r==source_map[r['sample_id']] for r in kept),'Defense relabelled a sample')
            rows.append(dict(dataset=source,strategy=strategy,training_samples=s['training_samples'],
                test_accuracy=s['test']['accuracy'],macro_f1=s['test']['macro_f1'],
                targeted_error=s['test']['targeted_0_to_1_rate'],
                accuracy_gain_pp=100*(s['test']['accuracy']-runs[source]['test']['accuracy']),
                poisoned_removed=len(removed&poisoned),clean_removed=len(removed-poisoned),remaining_poison=len(poisoned-removed)))
    write_json(OUT/'comparison.json',dict(status='VERIFIED',seed=2026,selection_plan_sha256=sha(DEST/'selection_plan.json'),rows=rows))
    chosen=read(DEST/'detector_selection.json')['chosen']
    lines=['# 实蝇标本分组检测与防御训练','',
        f"开发集选定 C={chosen['C']}，近邻/分类器/中心权重={chosen['weights']}，阈值={chosen['threshold']:.3f}。零权重信号不参与最终风险分数。",
        '保留原干净基线，新增3个投毒模型、8个语义/等量随机删除模型，共12组；seed=2026，20轮，完整独立测试集1321张。',
        '分类训练/验证/测试均按已确认标本编号隔离。新检测器也按标本交叉验证，近邻每个参考标本最多一票，分类器与类别中心均只使用参考折。',
        '检测参数仅在1392张验证图片及两组开发投毒实例上选择；同一验证集也用于分类检查点选择，最终测试集不用于调参。',
        '', '| 条件 | 策略 | 训练数 | 测试准确率 | Macro-F1 | correcta→zonata错误率 | 相对未处理准确率变化 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['dataset']} | {r['strategy']} | {r['training_samples']} | {r['test_accuracy']:.2%} | {r['macro_f1']:.4f} | {r['targeted_error']:.2%} | {r['accuracy_gain_pp']:+.2f} pp |")
    lines+=['','## 隔离代价','','| 条件 | 策略 | 移除投毒 | 误移除干净 | 剩余投毒 |','|---|---|---:|---:|---:|']
    for r in rows:
        if r['strategy']!='untreated':lines.append(f"| {r['dataset']} | {r['strategy']} | {r['poisoned_removed']} | {r['clean_removed']} | {r['remaining_poison']} |")
    detection=read(OUT/'detection_summary.json')
    old={r['dataset']:r for r in read(RESULTS/'semantic_evaluation_summary.json')['datasets']}
    lines+=['','## 检测效果与误报的取舍','','| 条件 | 旧召回 | 新召回 | 旧精确率 | 新精确率 | 旧干净误报 | 新干净误报 |','|---|---:|---:|---:|---:|---:|---:|']
    def pct(value):return '—' if value is None else f'{value:.2%}'
    for r in detection['results']:
        previous=old[r['dataset']]
        lines.append(f"| {r['dataset']} | {pct(previous['recall'])} | {pct(r['recall'])} | {pct(previous['precision'])} | {pct(r['precision'] if r['recall'] is not None else None)} | {pct(previous['clean_false_positive_rate'])} | {pct(r['clean_fpr'])} |")
    lines+=['','开发目标是误报约束下的平均F1，并非最大化召回；若新召回下降，必须连同精确率、误隔离成本和下游分类结果如实呈现。']
    lines+=['','## 解释边界','',
        '当前是单训练种子、固定一组攻击与随机删除实例。不可宣称普遍有效或统计显著。',
        '此前观察过旧实蝇攻击指标；本轮属于方法开发，不能描述为完全未见攻击的盲测。',
        '随机对照匹配删除总数，不匹配类别/标本分布；固定20轮使较小数据集拥有较少优化更新。',
        '开发集误报约束不等于部署保证；干净组准确率代价与投毒组恢复必须一起解释。',
        '原有语义检测器结果保留作历史记录；新旧差异同时涉及分组、权重、阈值和分类器配置，不能单独归因于某一个改变。','']
    (OUT/'defense_report_ZH.md').write_text('\n'.join(lines),encoding='utf-8')
    print('All 12 models verified; defense report saved.',flush=True)
    print(rows,flush=True)

if __name__=='__main__':main()
