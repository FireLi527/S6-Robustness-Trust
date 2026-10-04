"""Development-only block ablation; fixed existing model and threshold."""
import json
from pathlib import Path
import joblib
import numpy as np
from evaluate_repo_file_external_v1 import external_cases
from repo_file_blocks import score_documents
from train_repo_file_v1 import ROOT, MODEL, RESULTS, confusion, sha


def main():
    out = ROOT / 'results/bipia/repo_blocks_v2'
    if out.exists():
        raise FileExistsError('Do not overwrite diagnostic run')
    frozen = json.loads((RESULTS / 'validation.json').read_text(encoding='utf-8'))
    if sha(MODEL.read_bytes()) != frozen['model_sha256']:
        raise ValueError('Frozen model hash mismatch')
    human_path = ROOT / 'data/bipia/repo_file_review_v1/human_review_final.json'
    human = json.loads(human_path.read_text(encoding='utf-8'))
    if human['status'] != 'SINGLE_HUMAN_REVIEW_COMPLETE' or set(human['labels_by_sample_number'].values()) != {'benign_content'}:
        raise ValueError('Unexpected human labels')
    if sha((ROOT / human['source_samples']).read_bytes()) != human['source_samples_sha256']:
        raise ValueError('Human review source mismatch')
    bundle = joblib.load(MODEL)
    if bundle['threshold'] != frozen['threshold']:
        raise ValueError('Frozen threshold mismatch')
    cases = external_cases()
    scores = score_documents(bundle['pipeline'], [r['text'] for r in cases])
    rows = [{k:v for k,v in r.items() if k != 'text'} | s for r,s in zip(cases, scores)]
    for r in rows:
        if r['source'] == 'maintainer_candidates':
            r['label'] = 0
        r['full_flag'] = r['full_score'] >= bundle['threshold']
        r['block_flag'] = r['block_score'] >= bundle['threshold']
    groups = {}
    for source in sorted({r['source'] for r in rows}):
        subset = [r for r in rows if r['source'] == source]
        y = np.array([r['label'] for r in subset])
        groups[source] = {kind: confusion(y, np.array([r[kind + '_flag'] for r in subset])) for kind in ('full','block')}
    result = {'status':'DEVELOPMENT_DIAGNOSTIC_FIXED_OLD_THRESHOLD_NOT_CALIBRATED',
              'model_sha256':frozen['model_sha256'], 'threshold':bundle['threshold'],
              'extractor_sha256':sha((Path(__file__).parent / 'repo_file_blocks.py').read_bytes()),
              'human_review_sha256':sha(human_path.read_bytes()), 'sources':groups,
              'limitations':['Previously observed development data; not fresh confirmation.',
                             'Old full-document threshold reused only to diagnose score changes.',
                             'Block-max needs document-level threshold calibration before fair comparison.',
                             'Maintainer labels are single-user translated review; keyword-selected samples.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'predictions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 通用分块：开发诊断','', '采用冻结模型及旧全文阈值，只观察分块带来的变化；尚未重新校准，不能作为最终性能结论。', '',
           '| 数据 | 全文检出 | 分块检出 | 全文误报 | 分块误报 |','| --- | --- | --- | --- | --- |']
    for name, g in groups.items():
        a,b=g['full'],g['block']
        lines.append(f"| {name} | {a['tp']}/{a['tp']+a['fn']} | {b['tp']}/{b['tp']+b['fn']} | {a['fp']}/{a['fp']+a['tn']} | {b['fp']}/{b['fp']+b['tn']} |")
    lines += ['', '正常维护说明没有攻击样本，检出率栏的0/0表示不适用。分块取最大分数会增加告警机会，各组正式实验须独立在验证集上选择满足误报率约束的阈值。']
    (out/'report_ZH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
