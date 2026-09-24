"""Run the frozen specimen-group defense comparison with resumable completed runs."""
import json
import traceback
from pathlib import Path
import torch
import train_stl10_models as trainer
from prepare_fruitfly import DATA,IMAGES,RESULTS,sha,write_json
from prepare_fruitfly_grouped_defense import DEST,OUT,read


def require(ok,message):
    if not ok:raise ValueError(message)

def verify_run(s,base,manifest,expected_count):
    require(s['status']=='COMPLETE' and Path(s['checkpoint']).is_file(),'Incomplete model/checkpoint')
    require(s['trainer_sha256']==sha(Path(trainer.__file__))==base['trainer_sha256'],'Trainer changed')
    require(s['protocol_hash']==base['protocol_hash'],'Training protocol mismatch')
    require({k:v for k,v in s['protocol'].items() if k!='dataset'}=={k:v for k,v in base['protocol'].items() if k!='dataset'},'Hyperparameters changed')
    require(s['manifest_sha256']==sha(manifest),'Candidate manifest changed')
    require(s['training_samples']==expected_count,'Training sample count mismatch')
    for split,key in (('val','validation_split_sha256'),('test','test_split_sha256')):
        require(s[key]==sha(IMAGES/f'{split}.txt')==base[key],'Held-out split changed')
    require(s['validation_samples']==1392 and s['test_samples']==1321,'Incomplete held-out evaluation')


def main():
    plan=read(DEST/'selection_plan.json');experiment=read(DEST/'protocol.json')
    require(plan['experiment_sha256']==sha(DEST/'protocol.json'),'Frozen experiment changed')
    require(plan['selection_sha256']==sha(DEST/'detector_selection.json'),'Detector selection changed')
    require(plan['predictions_sha256']==sha(OUT/'candidate_predictions.json'),'Decisions changed')
    require(experiment['algorithm_sha256']==sha(Path(__file__).with_name('fruitfly_group_detector.py')),'Detector code changed')
    require(experiment['dataset_protocol_sha256']==sha(DATA/'protocol.json'),'Data protocol changed')
    base_paths=list((RESULTS/'model_training/clean_subset').glob('*/summary.json'))
    require(len(base_paths)==1,'Need exactly one verified clean baseline')
    base=read(base_paths[0])
    verify_run(base,base,DATA/'manifests/clean_subset.csv',6531)
    data_protocol=read(DATA/'protocol.json')
    from run_fruitfly import verify_inputs
    verify_inputs(data_protocol)
    trainer.IMAGE_ROOT=IMAGES;trainer.SELECTED_LABELS=tuple(range(5))
    trainer.LABEL_TO_INDEX={i:i for i in range(5)};trainer.INDEX_TO_LABEL={i:i for i in range(5)}
    require(torch.cuda.is_available(),'CUDA unavailable')
    jobs=[]
    for name in ('label_flip_05','label_flip_10','targeted_0_to_1'):
        jobs.append((name,DATA/'manifests'/f'{name}.csv',6531))
    # Complete each attack's equal-count random and semantic comparisons, then clean cost controls.
    for source in ('label_flip_05','label_flip_10','targeted_0_to_1','clean_subset'):
        for strategy in ('random','semantic'):
            name=f'{source}__{strategy}';v=plan['variants'][name]
            manifest=DEST/'manifests'/f'{name}.csv'
            require(sha(manifest)==v['manifest_sha256'],'Defense manifest changed')
            require(sha(DATA/'manifests'/f'{source}.csv')==v['source_manifest_sha256'],'Defense source changed')
            jobs.append((name,manifest,v['retained_samples']))
    summaries=[base]
    progress=OUT/'training_progress.json'
    def save(active=None):
        tmp=progress.with_suffix('.tmp.json')
        write_json(tmp,dict(status='COMPLETE' if len(summaries)==12 else 'RUNNING',active_condition=active,
          selection_plan_sha256=sha(DEST/'selection_plan.json'),runner_sha256=sha(Path(__file__)),
          completed_runs=len(summaries),expected_runs=12,summaries=summaries))
        tmp.replace(progress)
    save()
    for name,manifest,count in jobs:
        save(name);trainer.MANIFEST_ROOT=manifest.parent
        output=OUT/'model_training'
        previous=list((output/name).glob('*/summary.json'))
        require(len(previous)<=1,'Ambiguous previous model runs')
        if previous:
            summary=read(previous[0]);verify_run(summary,base,manifest,count)
            require(summary.get('defense_selection_sha256')==sha(DEST/'selection_plan.json'),'Existing run belongs to another selection')
            print('REUSE',name,flush=True)
        else:
            p=base['protocol']
            config=trainer.TrainingConfig(**{k:(name if k=='dataset' else p[k]) for k in trainer.TrainingConfig.__dataclass_fields__})
            print(f'START {len(summaries)+1}/12 {name} samples={count}',flush=True)
            summary=trainer.train_dataset(config,results_root=output,
                artifact_root=Path.home()/'s6-training-artifacts/fruitfly/grouped_defense_v1',device=torch.device('cuda'))
            verify_run(summary,base,manifest,count)
            summary.update(data_protocol='Fruitfly-confirmed-specimen-group-defense-v1',
                defense_selection_sha256=sha(DEST/'selection_plan.json'),fruitfly_protocol_sha256=sha(DATA/'protocol.json'),
                checkpoint_sha256=sha(Path(summary['checkpoint'])),runner_sha256=sha(Path(__file__)),
                targeted_metric_meaning='Bactrocera correcta classified as Bactrocera zonata')
            write_json(Path(summary['result_dir'])/'summary.json',summary)
        summaries.append(summary);save()
        print(f'COMPLETE {len(summaries)}/12 {name} accuracy={summary["test"]["accuracy"]:.6f}',flush=True)
    from report_fruitfly_defense import main as report
    report()

if __name__=='__main__':
    try:main()
    except Exception as error:
        write_json(OUT/'training_failure.json',dict(error=str(error),traceback=traceback.format_exc()))
        raise
