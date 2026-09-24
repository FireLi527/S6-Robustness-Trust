"""Independent fruit-fly transfer experiment using frozen STL-10 trainer/detector code."""
import argparse
import json
from pathlib import Path
import torch
import train_stl10_models as trainer
import evaluate_semantic as semantic
from prepare_fruitfly import DATA,IMAGES,RESULTS,CLASSES,sha,write_json
from manifest_protocol import load_candidate_manifest


def verify_inputs(protocol):
    if sha(DATA/'image_audit.csv')!=protocol['audit_sha256']:raise ValueError('Audit changed')
    import csv
    with (DATA/'image_audit.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    groups={s:set() for s in ('train','val','test')}
    pixels={s:set() for s in groups}
    for r in rows:
        if r['status']!='valid':continue
        if sha(IMAGES/r['source_relpath'])!=r['sha256']:raise ValueError('Image changed')
        groups[r['split']].add(r['group']);pixels[r['split']].add(r['pixel_sha256'])
    for a,b in (('train','val'),('train','test'),('val','test')):
        if groups[a]&groups[b] or pixels[a]&pixels[b]:raise ValueError('Cross-split leakage')
    for split,h in protocol['split_hashes'].items():
        if sha(IMAGES/f'{split}.txt')!=h:raise ValueError('Split changed')
    for name,meta in protocol['manifests'].items():
        if sha(DATA/'manifests'/f'{name}.csv')!=meta['sha256']:raise ValueError('Manifest changed')
    write_json(RESULTS/'input_verification.json',dict(status='VERIFIED',protocol_sha256=sha(DATA/'protocol.json'),
               checked_images=sum(len(s) for s in pixels.values()),disjoint_filename_groups=True,disjoint_exact_pixels=True,
               grouping_identity_unconfirmed=True,hidden_truth_used=False))


def evaluate_detector(protocol):
    output=RESULTS/'semantic_evaluation_summary.json'
    if output.exists():
        existing=json.loads(output.read_text(encoding='utf-8'))
        if existing['protocol_sha256']!=sha(DATA/'protocol.json') or existing['detector']!=semantic.detector_metadata():
            raise ValueError('Existing detector evaluation does not match protocol')
        print('Reusing completed semantic evaluation',flush=True);return
    semantic.GROUND_TRUTH_ROOT=DATA/'hidden_ground_truth'
    rows={name:load_candidate_manifest(DATA/'manifests'/f'{name}.csv') for name in protocol['manifests']}
    records=[semantic.blind_record_from_row(r) for r in rows['clean_subset']]
    embeddings=semantic.extract_embeddings(records,IMAGES,DATA/'embeddings/clip_vit_b32_embeddings.npz',semantic.CLIP_MODEL_CACHE)
    summaries=[];predictions={}
    for name,items in rows.items():
        summary,flagged,samples=semantic.evaluate_dataset(name,items,embeddings)
        summaries.append(summary);predictions[name]=samples
        print('SEMANTIC',json.dumps(summary),flush=True)
    payload=dict(dataset='Fruit-fly crops',protocol_sha256=sha(DATA/'protocol.json'),detector=semantic.detector_metadata(),
                 manifest_hashes={n:v['sha256'] for n,v in protocol['manifests'].items()},datasets=summaries,
                 limitations=['Thresholds unchanged from prior experiments; no tuning on fruit-fly results.',
                  'Candidate train images only; held-out classification val/test images not used by detector.',
                  'Detector OOF folds use individual images, not specimen groups; related views may share folds.',
                  'Filename grouping is an unverified identity proxy; exact duplicates excluded but near duplicates may remain.'])
    write_json(RESULTS/'semantic_sample_results.json',dict(detector=payload['detector'],protocol_sha256=payload['protocol_sha256'],datasets=predictions))
    write_json(output,payload)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true',help='Also train three poisoned-label models; default clean model only')
    args=parser.parse_args()
    protocol=json.loads((DATA/'protocol.json').read_text(encoding='utf-8'))
    verify_inputs(protocol)
    print('All imported image bytes and grouped splits verified',flush=True)
    evaluate_detector(protocol)
    trainer.IMAGE_ROOT=IMAGES;trainer.MANIFEST_ROOT=DATA/'manifests'
    trainer.SELECTED_LABELS=tuple(range(5));trainer.LABEL_TO_INDEX={i:i for i in range(5)};trainer.INDEX_TO_LABEL={i:i for i in range(5)}
    out=RESULTS/'model_training';artifacts=Path.home()/'s6-training-artifacts/fruitfly'
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    names=list(protocol['manifests']) if args.all else ['clean_subset']
    runs=[]
    for name in names:
        previous=list((out/name).glob('*/summary.json'))
        if len(previous)>1:raise ValueError('Ambiguous runs')
        if previous:
            summary=json.loads(previous[0].read_text(encoding='utf-8'))
            if (summary.get('fruitfly_protocol_sha256')!=sha(DATA/'protocol.json') or summary['status']!='COMPLETE'
                or summary['trainer_sha256']!=sha(Path(trainer.__file__)) or not Path(summary['checkpoint']).is_file()):
                raise ValueError('Existing model does not match inputs')
        else:
            config=trainer.TrainingConfig(name,2026,20,32,4,.0003,.0001,True,True,None,None)
            summary=trainer.train_dataset(config,results_root=out,artifact_root=artifacts,device=torch.device('cuda'))
            summary.update(fruitfly_protocol_sha256=sha(DATA/'protocol.json'),data_protocol='Fruitfly-inferred-filename-group-v1',
                           wrapper_sha256=sha(Path(__file__)),targeted_metric_meaning='Bactrocera correcta classified as Bactrocera zonata')
            write_json(Path(summary['result_dir'])/'summary.json',summary)
        runs.append(summary)
        write_json(out/'comparison_summary.json',dict(summaries=runs,protocol_sha256=sha(DATA/'protocol.json')))
    detector=json.loads((RESULTS/'semantic_evaluation_summary.json').read_text(encoding='utf-8'))
    lines=['# 小组实蝇数据首轮实验','',f"5类，ZIP原图{protocol['total_archive_images']}张，按推断文件名前9位编号分组。",
           '类别取自压缩包名称，未独立核验。编号分组不等同于已确认的标本独立划分。',
           'STL-10 基线与结果保留；本实验单独存储。','',
           '## 分类模型','', '| 条件 | 训练图片 | 验证图片 | 测试图片 | 测试准确率 | Macro-F1 |','|---|---:|---:|---:|---:|---:|']
    for s in runs:lines.append(f"| {s['dataset']} | {s['training_samples']} | {s['validation_samples']} | {s['test_samples']} | {s['test']['accuracy']:.2%} | {s['test']['macro_f1']:.4f} |")
    lines+=['','## 固定语义检测器迁移','', '| 条件 | 投毒数 | 检出精确率 | 投毒召回率 | 干净误报率 |','|---|---:|---:|---:|---:|']
    for s in detector['datasets']:lines.append(f"| {s['dataset']} | {s['poisoned_samples']} | {s['precision']} | {s['recall']} | {s['clean_false_positive_rate']:.2%} |")
    lines+=['','## 限制','',*detector['limitations'], '',
            '检测结果只使用候选训练图片；测试标签不用于调阈值。检测器内部按图片交叉验证，同组视角之间仍可能相关。',
            '本轮默认只训练干净分类模型，没有完成该数据集的防御后重训练或多种子验证。',
            '组间独立性需要同学确认命名规则后进一步核验；不能仅凭本轮高准确率宣称真实部署泛化。','']
    (RESULTS/'report_ZH.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Fruit-fly first-stage experiment COMPLETE',flush=True)

if __name__=='__main__':main()
