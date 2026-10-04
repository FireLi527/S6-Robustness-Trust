"""Hash and near-duplicate audit of pending authored candidates, no model fit."""
import json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from train_repo_file_v1 import ROOT, frozen_rows, sha
from evaluate_repo_file_external_v1 import external_cases, normalized


def main():
    source = ROOT / 'data/bipia/repo_file_v2/candidate_batch1.json'
    out = ROOT / 'results/bipia/repo_file_review_v2/batch1_audit.json'
    if out.exists():
        raise FileExistsError('Audit already exists')
    data = json.loads(source.read_text(encoding='utf-8'))
    rows = data['samples']
    assert len(rows) == 24 and len({r['sample_id'] for r in rows}) == 24
    assert sorted(r['review_number'] for r in rows) == list(range(1,25))
    assert all(r['reviewed_label'] is None and r['split'] is None for r in rows)
    assert {x: sum(r['proposed_label']==x for r in rows) for x in (0,1)} == {0:12,1:12}
    assert len({r['template_family'] for r in rows}) == 6
    for parent in {r['derivation_parent'] for r in rows}:
        siblings = [r for r in rows if r['derivation_parent'] == parent]
        assert len(siblings)==2 and len({r['split_group'] for r in siblings})==1
    _, old = frozen_rows()
    external = external_cases()
    reference = [{'id':f"v1/{r['split']}/{r['index']}", 'text':r['text']} for r in old]
    reference += [{'id':r['source']+'/'+r['id'], 'text':r['text']} for r in external]
    texts = [r['content'] for r in rows] + [r['text'] for r in reference]
    vectors = TfidfVectorizer(analyzer='char',ngram_range=(3,5),min_df=1).fit_transform(texts)
    similarity = (vectors[:24] @ vectors[24:].T).toarray()
    pair_similarity = (vectors[:24] @ vectors[:24].T).toarray()
    np.fill_diagonal(pair_similarity, 0)
    fingerprints = {sha(normalized(r['text']).encode()) for r in reference}
    checks=[]
    for i, row in enumerate(rows):
        best=int(np.argmax(similarity[i]))
        checks.append({'sample_id':row['sample_id'],'review_number':row['review_number'],
                       'content_sha256':sha(row['content'].encode()),
                       'translation_sha256':sha(row['translation_zh'].encode()),
                       'user_task_sha256':sha(row['user_task'].encode()),
                       'split_group':row['split_group'],
                       'exact_reference_overlap':sha(normalized(row['content']).encode()) in fingerprints,
                       'nearest_reference_id':reference[best]['id'],
                       'nearest_reference_similarity':float(similarity[i,best])})
    near_pairs=[{'a':rows[i]['sample_id'],'b':rows[j]['sample_id'],'cosine':float(pair_similarity[i,j]),
                 'same_group':rows[i]['split_group']==rows[j]['split_group']}
                for i in range(24) for j in range(i+1,24) if pair_similarity[i,j]>=.88]
    result={'status':'PENDING_HUMAN_REVIEW_AND_NEW_SOURCE_VALIDATION',
            'source_sha256':sha(source.read_bytes()),'sample_count':24,'family_count':6,
            'reference_count':len(reference),'duplicate_threshold':.88,
            'exact_reference_overlap_count':sum(r['exact_reference_overlap'] for r in checks),
            'near_reference_overlap_count':sum(r['nearest_reference_similarity']>=.88 for r in checks),
            'near_candidate_pairs':near_pairs,'samples':checks,
            'limitations':['AI-authored synthetic candidates; human labels pending.',
                           'Lexical duplicate checks cannot exclude semantic or attack-family overlap.',
                           'No model scores examined for candidate selection.',
                           'Candidate set is not a new independent external confirmation source.']}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
