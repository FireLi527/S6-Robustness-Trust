"""Audit pending batch 2 against frozen data and batch 1, without model scores."""
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from train_repo_file_v1 import ROOT, frozen_rows, sha
from evaluate_repo_file_external_v1 import external_cases, normalized


def main():
    src = ROOT / 'data/bipia/repo_file_v2/candidate_batch2.json'
    previous = ROOT / 'data/bipia/repo_file_v2/candidate_batch1.json'
    out = ROOT / 'results/bipia/repo_file_review_v2/batch2_audit.json'
    if out.exists():
        raise FileExistsError('Existing audit must be preserved')
    rows = json.loads(src.read_text(encoding='utf-8'))['samples']
    first = json.loads(previous.read_text(encoding='utf-8'))['samples']
    if len(rows) != 12 or len({r['sample_id'] for r in rows}) != 12:
        raise ValueError('Expected 12 unique samples')
    if sorted(r['review_number'] for r in rows) != list(range(1, 13)):
        raise ValueError('Review numbering changed')
    for row in rows:
        if row['split'] is not None or row['reviewed_label'] is not None:
            raise ValueError('Candidates must remain pending review and split')
        family_groups = {r['split_group'] for r in first + rows if r['template_family'] == row['template_family']}
        if len(family_groups) != 1:
            raise ValueError('Cross-batch family grouping mismatch')
    _, old = frozen_rows()
    refs = [{'id':f"v1/{r['split']}/{r['index']}", 'text':r['text']} for r in old]
    refs += [{'id':r['source']+'/'+r['id'], 'text':r['text']} for r in external_cases()]
    refs += [{'id':r['sample_id'], 'text':r['content']} for r in first]
    n = len(rows)
    x = TfidfVectorizer(analyzer='char', ngram_range=(3,5)).fit_transform(
        [r['content'] for r in rows] + [r['text'] for r in refs])
    scores = (x[:n] @ x[n:].T).toarray()
    reference_hashes = {sha(normalized(r['text']).encode()) for r in refs}
    checks = []
    for i,r in enumerate(rows):
        j = int(np.argmax(scores[i]))
        checks.append({'sample_id':r['sample_id'], 'review_number':r['review_number'],
                       'content_sha256':sha(r['content'].encode()),
                       'translation_sha256':sha(r['translation_zh'].encode()),
                       'task_sha256':sha(r['user_task'].encode()),
                       'exact_overlap':sha(normalized(r['content']).encode()) in reference_hashes,
                       'nearest_reference':refs[j]['id'], 'cosine':float(scores[i,j])})
    result = {'status':'PENDING_HUMAN_REVIEW', 'candidate_sha256':sha(src.read_bytes()),
              'batch1_sha256':sha(previous.read_bytes()), 'sample_count':n, 'reference_count':len(refs),
              'cross_batch_family_grouping_verified':True, 'duplicate_threshold':.88,
              'exact_overlap_count':sum(r['exact_overlap'] for r in checks),
              'near_overlap_count':sum(r['cosine']>=.88 for r in checks), 'samples':checks,
              'limitations':['Synthetic authored candidates; neither real-world prevalence nor an independent external test.',
                             'Lexical near-duplicate audit does not exclude semantic or family overlap.',
                             'No classifier scores inspected; human labels and dataset assignments still pending.']}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
