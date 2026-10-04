"""Post-hoc fixed-old-threshold diagnostic; does not select a new threshold."""
import json
import numpy as np
from train_repo_file_v1 import ROOT, confusion, sha


def main():
    out=ROOT/'results/bipia/repo_file_v2_development'
    path=out/'fixed_old_threshold.json'
    if path.exists():
        raise FileExistsError('Diagnostic already exists')
    source=out/'development_predictions.json'
    rows=json.loads(source.read_text(encoding='utf-8'))
    threshold=json.loads((ROOT/'results/bipia/repo_file_v1/validation.json').read_text(encoding='utf-8'))['threshold']
    arms={}
    for arm in sorted({r['arm'] for r in rows}):
        arms[arm]={}
        for dataset in sorted({r['source'] for r in rows}):
            subset=[r for r in rows if r['arm']==arm and r['source']==dataset]
            arms[arm][dataset]=confusion(np.array([r['label'] for r in subset]),np.array([r['score']>=threshold for r in subset]))
    path.write_text(json.dumps({'status':'POSTHOC_DIAGNOSTIC_NOT_MODEL_SELECTION','threshold':threshold,
                              'prediction_sha256':sha(source.read_bytes()),'arms':arms},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved fixed-old-threshold diagnostic; no refit, new threshold, or test scoring')


if __name__=='__main__':
    main()
