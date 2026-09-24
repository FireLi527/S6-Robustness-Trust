"""Read-only audit of frozen source splits, model and held-out predictions."""
import hashlib
import json
import numpy as np
import pandas as pd
from pathlib import Path
from supervised_data import ROOT, source_records, split_sources, catalogs, model_text
from train_supervised import source_batch, metrics
from supervised_detector import _load, ARTIFACT, SELECTION


def main():
    output=ROOT/"results/bipia/supervised"
    data=ROOT/"data/bipia/supervised"
    protocol=json.loads((data/"protocol.json").read_text(encoding="utf-8"))
    for relative,expected in protocol["input_hashes"].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,relative
    for name,expected in protocol["code_hashes"].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==expected,name
    rows,_=source_records(); splits=split_sources(rows); catalog,_,_=catalogs()
    actual={s:[{k:r[k] for k in ("source_id","group","task")} for r in rs] for s,rs in splits.items()}
    assert actual==json.loads((data/"source_splits.json").read_text(encoding="utf-8"))
    bundle,_=_load(ARTIFACT.stat().st_mtime_ns,SELECTION.stat().st_mtime_ns)
    frame=pd.read_csv(output/"test_predictions.csv",keep_default_na=False)
    offset=0
    for source in splits["test"]:
        batch=source_batch(source,catalog,"test")
        sub=frame.iloc[offset:offset+len(batch)]
        assert len(sub)==len(batch)
        assert (sub['source_id']==source['source_id']).all()
        assert (sub['group']==source['group']).all()
        assert (sub['task']==source['task']).all()
        for key in ('encoding','category','variant','position','label'):
            assert sub[key].tolist()==[r[key] for r in batch],key
        x=bundle['vectorizer'].transform(model_text(r['question'],r['context']) for r in batch)
        scores=bundle['model'].predict_proba(x)[:,1]
        assert np.allclose(scores,sub['supervised_score'],atol=1e-12,rtol=0)
        assert np.array_equal(scores>=bundle['threshold'],sub['supervised_detected'])
        offset+=len(batch)
    assert offset==len(frame)
    summary=json.loads((output/'summary.json').read_text(encoding='utf-8'))
    for row in summary['results']:
        sub=frame[(frame.task==row['task']) & frame.encoding.isin([row['encoding'],'clean'])]
        # Optional columns have blank non-email values; normalise CSV boolean strings.
        detected=sub[row['system']+'_detected'].map(lambda x:x is True or str(x)=='True')
        scored=metrics(sub.label.tolist(),detected.tolist(),sub.supervised_score.tolist() if row['system']=='supervised' else None)
        for key,value in scored.items():
            assert abs(row[key]-value)<1e-12,(row['task'],row['system'],key)
    counts={}
    for split in ('train','validation','test'):
        counts[split]={task:{'sources':sum(s['task']==task for s in splits[split]),
                      'attack_variants':sum(len(source_batch(s,catalog,split))-1 for s in splits[split] if s['task']==task)}
                      for task in ('email','table','code')}
    result=dict(status='VERIFIED',test_prediction_rows=offset,counts=counts,
                checks=['source hashes','training code hashes','source-content separation','checkpoint hash',
                        'all held-out model scores replayed','summary metrics recomputed'],
                model_sha256=hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(),
                predictions_sha256=hashlib.sha256((output/'test_predictions.csv').read_bytes()).hexdigest())
    (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
