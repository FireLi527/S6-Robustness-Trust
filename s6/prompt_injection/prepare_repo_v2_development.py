"""Freeze reviewed augmentation and cross-source validation for exploratory fitting."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from train_repo_file_v1 import ROOT, frozen_rows, sha


def main():
    data = ROOT / 'data/bipia/repo_file_v2'
    output = data / 'development_protocol.json'
    if output.exists():
        raise FileExistsError('Development protocol already frozen')
    human_path = data / 'human_review_completion.json'
    human = json.loads(human_path.read_text(encoding='utf-8'))
    inputs = {str(human_path.relative_to(ROOT)):sha(human_path.read_bytes())}
    aug=[]
    for batch in ('batch1','batch2'):
        path=data/f'candidate_{batch}.json'
        if sha(path.read_bytes())!=human[batch]['candidate_sha256']:
            raise ValueError('Candidate hash mismatch')
        inputs[str(path.relative_to(ROOT))]=sha(path.read_bytes())
        rows=json.loads(path.read_text(encoding='utf-8'))['samples']
        normal=set(human[batch]['benign']); attack=set(human[batch]['injection'])
        if normal & attack or normal | attack != {r['review_number'] for r in rows}:
            raise ValueError('Labels must cover each sample exactly once')
        for r in rows:
            label=int(r['review_number'] in attack)
            aug.append({'sample_id':r['sample_id'],'text':r['content'],'label':label,
                        'source':batch,'split':'train','group_id':r['split_group'],
                        'content_sha256':sha(r['content'].encode()),
                        'annotation':'single user reviewed Chinese translation with task context'})
    source_manifest=data/'agentic5k_source_manifest.json'
    source=json.loads(source_manifest.read_text(encoding='utf-8'))
    inputs[str(source_manifest.relative_to(ROOT))]=sha(source_manifest.read_bytes())
    val_path=ROOT/'external/agentic-prompt-injection-5k/data/validation.parquet'
    if sha(val_path.read_bytes())!=source['files']['data/validation.parquet']['sha256']:
        raise ValueError('Validation source hash mismatch')
    inputs[str(val_path.relative_to(ROOT))]=sha(val_path.read_bytes())
    frame=pd.read_parquet(val_path)
    if len(frame)!=467 or set(frame['label'])!={0,1}:
        raise ValueError('Unexpected validation rows')
    protocol,old=frozen_rows()
    old_train=[r for r in old if r['split']=='train']
    old_val=[r for r in old if r['split']=='validation']
    train=old_train+aug
    # Audit new-source validation against actual proposed training texts only.
    corpus=[r['text'] for r in train]+list(frame['text'])
    vectors=TfidfVectorizer(analyzer='char',ngram_range=(3,5)).fit_transform(corpus)
    similarity=(vectors[len(train):] @ vectors[:len(train)].T).toarray()
    maxima=similarity.max(axis=1)
    excluded=np.flatnonzero(maxima>=.88).tolist()
    accepted=[i for i in range(len(frame)) if i not in excluded]
    rows=[{'source_row':int(i),'id':str(frame.iloc[i]['id']),
           'label':int(frame.iloc[i]['label']), 'content_sha256':sha(frame.iloc[i]['text'].encode())}
          for i in accepted]
    if any(sum(r['label']==c for r in rows)==0 for c in (0,1)):
        raise ValueError('Both labels required after overlap exclusion')
    aug_path=data/'reviewed_augmentation.json'
    aug_path.write_text(json.dumps(aug,ensure_ascii=False,indent=2),encoding='utf-8')
    inputs[str(aug_path.relative_to(ROOT))]=sha(aug_path.read_bytes())
    result={'status':'FROZEN_BEFORE_EXPLORATORY_FIT','scope':'DEVELOPMENT_ONLY_NO_FINAL_CONFIRMATION',
            'input_sha256':inputs,'original_source_sha256':protocol['source_sha256'],
            'original_assignments_sha256':protocol['assignments_sha256'],
            'train_original':len(old_train),'train_augmented':len(train),'augmentation_count':len(aug),
            'validation_original':len(old_val),'validation_new_source':rows,
            'near_duplicate_threshold':.88,'new_validation_excluded_near_train':excluded,
            'new_validation_max_train_similarity':float(maxima.max()),
            'group_policy':'All 36 authored samples across both batches assigned to train. Shared families never split. New public source used only for validation in this run.',
            'fit_policy':'Same v1 TF-IDF + LogisticRegression settings, equal sample weights; C and D share a single refit.',
            'threshold_policy':'For each arm maximize mean source recall subject to FPR <=5% in EACH of original validation and new-source validation; tie: lower mean FPR then higher threshold; include reject-all threshold.',
            'diagnostic_policy':'After threshold freeze, score only previously observed external development sets. No fresh-test claim.',
            'held_out_policy':'Do not read or score agentic5k test or original internal test in this run.',
            'final_confirmation_status':'NEW_INDEPENDENT_SOURCE_STILL_PENDING',
            'limitations':['Only 36 new synthetic authored examples, not a large independent corpus.',
                           'Public validation is mixed-domain synthetic text with publisher labels, not repository-only.',
                           'Original v1 data lacks source-family metadata; near-duplicate grouping does not guarantee family isolation.',
                           'Human labels used task context while content classifier sees only text.']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_sha256','validation_new_source')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
