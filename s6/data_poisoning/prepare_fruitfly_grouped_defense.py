"""Calibrate specimen-disjoint detector on validation only, then freeze train selections."""
import csv,json,random
from pathlib import Path
from collections import Counter
import numpy as np
from prepare_fruitfly import DATA,IMAGES,RESULTS,sha,write_json,write_csv
from manifest_protocol import load_candidate_manifest,CANDIDATE_FIELDS
from semantic_detector import SemanticInputRecord,extract_embeddings,detector_metadata
from fruitfly_group_detector import GroupedInput,group_id,signals,decisions
from prepare_stl10_defense import select_rows

DEST=DATA/'grouped_defense_v1'
OUT=RESULTS/'grouped_defense_v1'
NAMES=('clean_subset','label_flip_05','label_flip_10','targeted_0_to_1')
WEIGHTS=((.4,.4,.2),(.25,.75,0.),(0.,1.,0.),(.5,.5,0.))
CS=(1.,10.)
SEEDS=(52026,52027)

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def frozen_json(path,value):
    if path.exists() and read(path)!=value:raise ValueError(f'Frozen artifact differs: {path}')
    write_json(path,value)

def rate_metrics(y,flag):
    y=np.asarray(y,dtype=bool);flag=np.asarray(flag,dtype=bool)
    tp=int((y&flag).sum());fp=int((~y&flag).sum());fn=int((y&~flag).sum());tn=int((~y&~flag).sum())
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,recall=tp/(tp+fn) if tp+fn else None,
                precision=tp/(tp+fp) if tp+fp else 0.,f1=2*tp/max(2*tp+fp+fn,1),clean_fpr=fp/max(fp+tn,1))

def development_cases(rows):
    cases={'clean':(rows,np.zeros(len(rows),dtype=bool))}
    for seed in SEEDS:
        for name,rate in (('label_flip_05',.05),('label_flip_10',.1),('targeted_0_to_1',.2)):
            rng=random.Random(seed)
            eligible=[i for i,r in enumerate(rows) if name!='targeted_0_to_1' or r['assigned_label']=='0']
            selected=set(rng.sample(eligible,round(rate*len(eligible))))
            candidate=[]
            for i,r in enumerate(rows):
                label=r['assigned_label']
                if i in selected:label='1' if name=='targeted_0_to_1' else rng.choice([str(v) for v in range(5) if str(v)!=label])
                candidate.append(dict(r,assigned_label=label))
            cases[f'{name}_seed{seed}']=(candidate,np.array([i in selected for i in range(len(rows))]))
    return cases

def inputs(rows):
    return [GroupedInput(r['sample_id'],r['sha256'],r['assigned_label'],group_id(Path(r['source_relpath']).name)) for r in rows]

def main():
    protocol=read(DATA/'protocol.json');confirmation=read(DATA/'specimen_group_confirmation.json')
    assert confirmation['applies_to_protocol_sha256']==sha(DATA/'protocol.json')
    assert sha(DATA/'image_audit.csv')==protocol['audit_sha256']
    for name,info in protocol['manifests'].items():
        assert sha(DATA/'manifests'/f'{name}.csv')==info['sha256']
    experiment=dict(dataset_protocol_sha256=sha(DATA/'protocol.json'),confirmation_sha256=sha(DATA/'specimen_group_confirmation.json'),
        algorithm_sha256=sha(Path(__file__).with_name('fruitfly_group_detector.py')),preparation_sha256=sha(Path(__file__)),
        embedding_configuration=detector_metadata(),development_split='existing classifier validation only; no test images',
        development_poison_seeds=list(SEEDS),classifier_C=list(CS),weights=[list(w) for w in WEIGHTS],
        thresholds=[float(t) for t in np.r_[np.arange(.3,1.,.025),1.000001]],
        criterion='Max mean development F1 across six attack cases, subject to <=5% clean development FPR; tie lower FPR then higher threshold',
        policy='Retain ALLOW only; REVIEW withheld, no relabelling',random_removal_seed=32026,
        classifier_epochs=20,classifier_seed=2026,
        limitations=['Validation set reused for detector development and downstream checkpoint selection; final test never used to tune.',
                     'Prior fruit-fly attack results were observed; this is development, not a pristine blind evaluation.',
                     'One training seed and one random-removal seed; fixed epochs imply different update counts.'])
    frozen_json(DEST/'protocol.json',experiment)
    if (DEST/'selection_plan.json').exists():
        plan=read(DEST/'selection_plan.json')
        assert plan['experiment_sha256']==sha(DEST/'protocol.json')
        for name,v in plan['variants'].items():assert sha(DEST/'manifests'/f'{name}.csv')==v['manifest_sha256']
        print('Frozen grouped-defense selection already complete',flush=True);return
    with (DATA/'image_audit.csv').open(encoding='utf-8-sig') as f:audit=list(csv.DictReader(f))
    dev=[dict(sample_id='dev_'+Path(r['filename']).stem,source_relpath=r['source_relpath'],sha256=r['sha256'],assigned_label=r['label'])
         for r in audit if r['status']=='valid' and r['split']=='val']
    cases=development_cases(dev)
    for name,(rows,truth) in cases.items():
        write_csv(DEST/'development/manifests'/f'{name}.csv',rows,CANDIDATE_FIELDS)
        write_json(DEST/'development/truth'/f'{name}.json',{r['sample_id']:bool(y) for r,y in zip(rows,truth)})
    records=[SemanticInputRecord(**r) for r in dev]
    embeddings=extract_embeddings(records,IMAGES,DEST/'development/clip_embeddings.npz',DATA.parents[1]/'external/clip_cache')
    best=None;trials=[]
    for c in CS:
        matrices={}
        for name,(rows,truth) in cases.items():
            matrix,folds=signals(inputs(rows),embeddings,c)
            matrices[name]=matrix
            npz=DEST/'development/signals';npz.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(npz/f'{name}_C{c}.npz',signals=matrix,folds=folds)
            print(f'DEVELOPMENT C={c} case={name}',flush=True)
        for weights in WEIGHTS:
            risks={name:m@np.asarray(weights) for name,m in matrices.items()}
            for threshold in experiment['thresholds']:
                fpr=float(np.mean(risks['clean']>=threshold))
                if fpr>.05:continue
                scores=[rate_metrics(cases[n][1],r>=threshold) for n,r in risks.items() if n!='clean']
                value=float(np.mean([s['f1'] for s in scores]))
                trial=dict(C=c,weights=list(weights),threshold=threshold,development_mean_f1=value,clean_fpr=fpr)
                trials.append(trial)
                key=(value,-fpr,threshold)
                if best is None or key>best[0]:best=(key,trial)
    chosen=best[1]
    frozen_json(DEST/'detector_selection.json',dict(experiment_sha256=sha(DEST/'protocol.json'),chosen=chosen,trials=trials))
    print('DETECTOR FROZEN',json.dumps(chosen),flush=True)
    originals={name:load_candidate_manifest(DATA/'manifests'/f'{name}.csv') for name in NAMES}
    all_records=[SemanticInputRecord(**r) for r in originals['clean_subset']]
    embeddings=extract_embeddings(all_records,IMAGES,DATA/'embeddings/clip_vit_b32_embeddings.npz',DATA.parents[1]/'external/clip_cache')
    predictions={}
    for name,rows in originals.items():
        records=inputs(rows);matrix,folds=signals(records,embeddings,chosen['C'])
        predictions[name]=decisions(records,matrix,chosen['weights'],chosen['threshold'])
        for r,fold in zip(records,folds):predictions[name][r.sample_id]['held_out_fold']=int(fold)
        print('CANDIDATE',name,dict(Counter(v['decision'] for v in predictions[name].values())),flush=True)
    prediction_path=OUT/'candidate_predictions.json'
    frozen_json(prediction_path,dict(experiment_sha256=sha(DEST/'protocol.json'),selection_sha256=sha(DEST/'detector_selection.json'),datasets=predictions))
    plan=dict(experiment_sha256=sha(DEST/'protocol.json'),selection_sha256=sha(DEST/'detector_selection.json'),
              predictions_sha256=sha(prediction_path),variants={},hidden_truth_used_for_selection=False)
    for index,name in enumerate(NAMES):
        for strategy,(kept,removed) in select_rows(originals[name],predictions[name],32026+index).items():
            if {r['assigned_label'] for r in kept}!=set(map(str,range(5))):raise ValueError('Selection removed a class')
            variant=f'{name}__{strategy}';path=DEST/'manifests'/f'{variant}.csv'
            write_csv(path,kept,CANDIDATE_FIELDS)
            plan['variants'][variant]=dict(source_dataset=name,strategy=strategy,retained_samples=len(kept),removed_count=len(removed),
                removed_sample_ids=removed,source_manifest_sha256=sha(DATA/'manifests'/f'{name}.csv'),manifest_sha256=sha(path))
    frozen_json(DEST/'selection_plan.json',plan)
    # Only after all decisions AND selection manifests are frozen, open train scoring truth.
    from manifest_protocol import load_hidden_ground_truth,validate_candidate_truth_pair
    scored=[]
    for name,rows in originals.items():
        truth=validate_candidate_truth_pair(rows,load_hidden_ground_truth(DATA/'hidden_ground_truth'/f'{name}.csv'))
        y=[truth[r['sample_id']]['poisoned']=='true' for r in rows]
        flags=[predictions[name][r['sample_id']]['decision']!='ALLOW' for r in rows]
        scored.append(dict(dataset=name,**rate_metrics(y,flags)))
    write_json(OUT/'detection_summary.json',dict(chosen=chosen,results=scored,selection_plan_sha256=sha(DEST/'selection_plan.json')))
    print('ALL SELECTIONS FROZEN',json.dumps(scored),flush=True)

if __name__=='__main__':main()
