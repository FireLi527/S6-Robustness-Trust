"""Four-arm exploratory comparison; no fresh test set is evaluated."""
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from train_repo_file_v1 import ROOT, MODEL, frozen_rows, make_pipeline, confusion, sha
from repo_file_blocks import score_documents
from evaluate_repo_file_external_v1 import external_cases

DATA=ROOT/'data/bipia/repo_file_v2'
OUT=ROOT/'results/bipia/repo_file_v2_development'
SCRIPT=Path(__file__)


def write(name,value):
    path=OUT/name
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def select_by_source(labels,scores,sources):
    groups=sorted(set(sources))
    masks={g:np.asarray(sources)==g for g in groups}
    if any(set(labels[m])!={0,1} for m in masks.values()):
        raise ValueError('Each validation source must contain both labels')
    candidates=[float(np.nextafter(max(scores),np.inf))]+sorted(set(float(v) for v in scores),reverse=True)
    best=None
    for threshold in candidates:
        metrics={g:confusion(labels[m],scores[m]>=threshold) for g,m in masks.items()}
        if any(v['fpr']>.05 for v in metrics.values()):
            continue
        key=(np.mean([v['recall'] for v in metrics.values()]),-np.mean([v['fpr'] for v in metrics.values()]),threshold)
        if best is None or key>best[0]:
            best=(key,threshold,metrics)
    return best[1],best[2]


def inputs():
    p=json.loads((DATA/'development_protocol.json').read_text(encoding='utf-8'))
    for path,digest in p['input_sha256'].items():
        if sha((ROOT/path).read_bytes())!=digest:
            raise ValueError(f'Input changed: {path}')
    old_protocol,old=frozen_rows()  # Entire v1 file hash-checked; test rows unused.
    if old_protocol['source_sha256']!=p['original_source_sha256'] or old_protocol['assignments_sha256']!=p['original_assignments_sha256']:
        raise ValueError('Original data provenance changed')
    aug=json.loads((DATA/'reviewed_augmentation.json').read_text(encoding='utf-8'))
    original_val=[r for r in old if r['split']=='validation']
    frame=pd.read_parquet(ROOT/'external/agentic-prompt-injection-5k/data/validation.parquet')
    public_val=[]
    for assigned in p['validation_new_source']:
        row=frame.iloc[assigned['source_row']]
        if sha(row['text'].encode())!=assigned['content_sha256'] or int(row['label'])!=assigned['label']:
            raise ValueError('New validation assignment changed')
        public_val.append({'text':row['text'],'label':int(row['label'])})
    return p,[r for r in old if r['split']=='train']+aug,original_val+public_val, ['repo_v1']*len(original_val)+['agentic5k']*len(public_val)


def tracked_hashes():
    paths=[SCRIPT,Path(__file__).with_name('repo_file_blocks.py'),Path(__file__).with_name('train_repo_file_v1.py'),DATA/'development_protocol.json',MODEL]
    return {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in paths}


def freeze():
    if OUT.exists():
        raise FileExistsError('Development run already exists')
    p,train,val,sources=inputs()
    OUT.mkdir(parents=True)
    write('selection.json',{'status':'FROZEN_BEFORE_FITTING','hashes':tracked_hashes(),
          'training_rows':len(train),'validation_rows':len(val),'arms':['A_full_frozen','B_blocks_frozen','C_full_augmented','D_blocks_augmented'],
          'policy':p['threshold_policy'],'augmentation_weight':1.0,
          'scope':'EXPLORATORY_DEVELOPMENT_NO_INDEPENDENT_TEST',
          'holdout_clarification':'v1 integrity loader reads source bytes to validate hashes; test rows are not fitted, calibrated, scored, or inspected for examples. agentic5k test parquet is not opened.'})
    print('FROZEN four-arm development specification')


def check_freeze():
    frozen=json.loads((OUT/'selection.json').read_text(encoding='utf-8'))
    if frozen['hashes']!=tracked_hashes():
        raise ValueError('Frozen code or inputs changed')


def fit():
    check_freeze()
    if (OUT/'model.joblib').exists() or (OUT/'validation.json').exists():
        raise FileExistsError('Fit already exists')
    _,train,val,sources=inputs()
    refit=make_pipeline()
    refit.fit([r['text'] for r in train],[r['label'] for r in train])
    joblib.dump(refit,OUT/'model.joblib')
    baseline=joblib.load(MODEL)['pipeline']
    arms={}; prediction_rows=[]
    y=np.array([r['label'] for r in val])
    for weights,pipe in [('frozen',baseline),('augmented',refit)]:
        predictions=score_documents(pipe,[r['text'] for r in val])
        for mode in ('full','blocks'):
            prefix={('frozen','full'):'A',('frozen','blocks'):'B',('augmented','full'):'C',('augmented','blocks'):'D'}[(weights,mode)]
            name=f'{prefix}_{mode}_{weights}'
            scores=np.array([r['full_score' if mode=='full' else 'block_score'] for r in predictions])
            threshold,metrics=select_by_source(y,scores,sources)
            arms[name]={'threshold':threshold,'validation_by_source':metrics}
            prediction_rows.extend({'arm':name,'row':i,'source':sources[i],'label':int(y[i]),'score':float(score)} for i,score in enumerate(scores))
    write('validation_predictions.json',prediction_rows)
    write('validation.json',{'status':'THRESHOLDS_FROZEN_BEFORE_DEVELOPMENT_DIAGNOSTICS',
          'model_sha256':sha((OUT/'model.joblib').read_bytes()),'arms':arms})
    print(json.dumps(arms,ensure_ascii=False,indent=2))


def diagnose():
    check_freeze()
    if (OUT/'development_comparison.json').exists():
        raise FileExistsError('Development comparison already exists')
    validation=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
    if sha((OUT/'model.joblib').read_bytes())!=validation['model_sha256']:
        raise ValueError('Refit model changed')
    cases=external_cases()
    for r in cases:
        if r['source']=='maintainer_candidates':
            r['label']=0
    baseline=joblib.load(MODEL)['pipeline']; refit=joblib.load(OUT/'model.joblib')
    output={}; records=[]
    for weights,pipe in [('frozen',baseline),('augmented',refit)]:
        predictions=score_documents(pipe,[r['text'] for r in cases])
        for mode in ('full','blocks'):
            prefix={('frozen','full'):'A',('frozen','blocks'):'B',('augmented','full'):'C',('augmented','blocks'):'D'}[(weights,mode)]
            name=f'{prefix}_{mode}_{weights}'; threshold=validation['arms'][name]['threshold']
            scores=np.array([r['full_score' if mode=='full' else 'block_score'] for r in predictions])
            groups={}
            for source in sorted({r['source'] for r in cases}):
                mask=np.array([r['source']==source for r in cases])
                y=np.array([r['label'] for r in cases])[mask]
                groups[source]=confusion(y,scores[mask]>=threshold)
            output[name]={'threshold':threshold,'sources':groups}
            records.extend({'arm':name,'source':r['source'],'id':r['id'],'label':r['label'],'score':float(score),'flag':bool(score>=threshold)} for r,score in zip(cases,scores))
    write('development_predictions.json',records)
    write('development_comparison.json',{'status':'COMPLETE_DEVELOPMENT_ONLY','arms':output,'fresh_external_test':None})
    lines=['# 第二轮四组开发对照','', '36条合成样本已由用户审核，补充训练集共3438条；阈值在原验证集1134条和新来源验证集467条上选择，要求两个来源各自误报率不超过5%。', '',
           '以下均为已经观察过的开发诊断数据，不是独立外部确认。A/B也重新校准了阈值，不能直接与第一轮旧阈值成绩相比。', '',
           '| 组别 | 阈值 | RepoGuard检出 | RepoGuard误报 | AIB检出 | AIB误报 | 维护说明误报 |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for name,item in output.items():
        r=item['sources']['RepoGuardBench']; a=item['sources']['AgentInjectionBench']; m=item['sources']['maintainer_candidates']
        lines.append(f"| {name} | {item['threshold']:.4f} | {r['tp']}/470 | {r['fp']}/94 | {a['tp']}/8 | {a['fp']}/2 | {m['fp']}/30 |")
    lines += ['', 'A：原模型全文；B：原模型分块；C：补数据模型全文；D：补数据模型分块。分块模型使用全文和通用注释/段落视图的最大分数。', '',
              '公共验证来源：[Agentic Prompt-Injection 5K](https://huggingface.co/datasets/3nesdeniz/agentic-prompt-injection-5k)，Enes Deniz，CC-BY-4.0；它是混合场景合成数据，不是纯仓库文件。', '',
              '该来源的测试文件仅下载保留，本轮未打开或评分；它与其验证集同源，也不能单独充当全新来源确认。另需独立来源才能作最终泛化结论。尚未修改前端默认检测或工具授权。']
    (OUT/'report_ZH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['freeze','fit','diagnose'])
    args=parser.parse_args()
    {'freeze':freeze,'fit':fit,'diagnose':diagnose}[args.mode]()
