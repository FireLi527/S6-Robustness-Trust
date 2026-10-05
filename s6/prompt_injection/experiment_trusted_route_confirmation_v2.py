"""Predeclared frozen-route test on new human-reviewed bilingual controls."""
from __future__ import annotations

import argparse
from pathlib import Path
from s6.engineering.artifacts import file_sha256,new_run,read_json,require_hash,write_json
from s6.prompt_injection.content_probe_v1 import summarize
from s6.prompt_injection.reviewer_ablation_v1 import messages_for,parse_output
from s6.prompt_injection.trusted_review_route_v1 import task_profile
from s6.prompt_injection.trusted_review_runtime_v1 import routed_batches,resolved_record,infer_routed_batch

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT/'data/bipia/trusted_route_confirmation_candidates_v2'
REVIEW = ROOT/'data/bipia/trusted_route_confirmation_review_v2/human_review.json'
DATA = ROOT/'data/bipia/trusted_route_confirmation_v2'
OUT = ROOT/'results/bipia/trusted_route_confirmation_v2'


def prepare() -> None:
    """Require direct semantic review before proposed labels become human truth."""
    for name,digest in read_json(CANDIDATES/'integrity.json').items():
        require_hash(CANDIDATES/name,digest)
    review = read_json(REVIEW)
    require_hash(CANDIDATES/'candidates.json',review['candidate_sha256'])
    raw = read_json(CANDIDATES/'candidates.json')
    if review['authority']!='direct user message in this thread' or set(review['approved_ids'])!={r['id'] for r in raw}:
        raise ValueError('Complete direct human review required')
    labels = review['labels']
    if set(labels)!={r['id'] for r in raw} or any(v not in {'NORMAL','RISK','UNKNOWN'} for v in labels.values()):
        raise ValueError('Explicit reviewed labels required')
    rows = [{**r,'expected':labels[r['id']],'human_reviewed':True} for r in raw]
    prior = read_json(CANDIDATES/'protocol.json')
    for n,digest in prior['code_sha256'].items():
        require_hash(Path(__file__).with_name(n),digest)
    baseline = read_json(ROOT/'data/bipia/trusted_review_live_v1/protocol.json')
    code = ('experiment_trusted_route_confirmation_v2.py','trusted_review_runtime_v1.py',
            'trusted_review_route_v1.py','reviewer_ablation_v1.py','content_probe_v1.py')
    with new_run(DATA,{'purpose':'New human-reviewed assistant-authored bilingual controlled confirmation; not natural distribution or blind authorship',
         'candidate_protocol_sha256':file_sha256(CANDIDATES/'protocol.json'),
         'review_sha256':file_sha256(REVIEW),'criteria':prior['criteria'],
         'spec':baseline['spec'],'model_hashes':baseline['model_hashes'],
         'code_sha256':{n:file_sha256(Path(__file__).with_name(n)) for n in code},
         'selection':'Single predeclared frozen-route candidate; no repairs, no model choice or rule tuning against these outputs'}):
        write_json(DATA/'rows.json',rows)
        write_json(DATA/'integrity.json',{'rows.json':file_sha256(DATA/'rows.json')})


def inputs() -> tuple[dict,list[dict]]:
    """Validate reviewed materials and unchanged model/runtime identities."""
    p = read_json(DATA/'protocol.json')
    if read_json(DATA/'status.json')['state']!='COMPLETE':
        raise ValueError('Confirmation freeze incomplete')
    require_hash(DATA/'rows.json',read_json(DATA/'integrity.json')['rows.json'])
    require_hash(REVIEW,p['review_sha256'])
    require_hash(CANDIDATES/'protocol.json',p['candidate_protocol_sha256'])
    for n,digest in p['code_sha256'].items():
        require_hash(Path(__file__).with_name(n),digest)
    return p,read_json(DATA/'rows.json')


def metrics(raw: list[dict],rows: list[dict]) -> dict:
    """Keep languages, model signals and policy readiness separately visible."""
    decisions = [resolved_record(row,r) for row,r in zip(rows,raw,strict=True)]
    groups = {r['group_id'] for r in rows}
    lookup = {r['id']:r for r in decisions}
    result = {'resolved':summarize(decisions),'model_signals':summarize(raw),
              'all_four_correct':{'hits':sum(all(lookup[r['id']]['decision']==r['expected'] for r in rows if r['group_id']==g) for g in groups),'n':len(groups)}}
    result['per_language'] = {lang:{'resolved':summarize([d for d,row in zip(decisions,rows,strict=True) if row['language']==lang]),
                'model_signals':summarize([d for d,row in zip(raw,rows,strict=True) if row['language']==lang])}
                for lang in ('en','zh')}
    return result


def run() -> None:
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig
    p,rows = inputs()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    path = ROOT/p['spec']['model']
    for n,digest in p['model_hashes'].items():
        require_hash(path/n,digest)
    with new_run(OUT,{'data_protocol_sha256':file_sha256(DATA/'protocol.json'),'model_hashes':p['model_hashes'],
                     'cache_reuse':False,'training':False,'batch_size':4}):
        t = AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16),
            device_map={'':0},dtype=torch.bfloat16,attn_implementation='sdpa').eval()
        model.requires_grad_(False)
        records = {}
        for head,batch in routed_batches(rows):
            for r in infer_routed_batch(model,t,batch,head,p['spec']):
                records[r['id']] = r
                write_json(OUT/'raw'/(r['id']+'.json'),r)
            print(f'New bilingual confirmation {len(records)}/{len(rows)}',flush=True)
        raw = [records[r['id']] for r in rows]
        write_json(OUT/'predictions.json',raw)
        write_json(OUT/'decisions.json',[resolved_record(row,r) for row,r in zip(rows,raw,strict=True)])
        write_json(OUT/'summary.json',metrics(raw,rows))


def verify() -> None:
    from transformers import AutoTokenizer
    p,rows = inputs()
    if read_json(OUT/'status.json')['state']!='COMPLETE':
        raise ValueError('Confirmation inference incomplete')
    require_hash(DATA/'protocol.json',read_json(OUT/'protocol.json')['data_protocol_sha256'])
    path = ROOT/p['spec']['model']
    for n,digest in p['model_hashes'].items():
        require_hash(path/n,digest)
    t = AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
    with new_run(OUT/'verification',{'limits':'Full input/output/evidence/policy/metric replay; no natural generalization or semantic evidence certificate'}):
        raw = read_json(OUT/'predictions.json')
        if [r['id'] for r in raw]!=[r['id'] for r in rows]:
            raise ValueError('Coverage mismatch')
        for row,r in zip(rows,raw,strict=True):
            head = task_profile(row['task'])['head']
            ids = t.apply_chat_template(messages_for(row,head),tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
            if r['input_ids']!=ids or r['input_tokens']!=len(ids) or r['arm']!=head or r['source']!=row['source'] or r['expected']!=row['expected']:
                raise ValueError('Input/head/label mismatch')
            if read_json(OUT/'raw'/(r['id']+'.json'))!=r or t.decode(r['generated_token_ids'],skip_special_tokens=True)!=r['text']:
                raise ValueError('Raw/decode mismatch')
            finished = bool(r['generated_token_ids']) and r['generated_token_ids'][-1]==t.eos_token_id
            if r['finished']!=finished or len(r['generated_token_ids'])>p['spec']['max_new_tokens'] or len(ids)+p['spec']['max_new_tokens']>p['spec']['total_budget']:
                raise ValueError('EOS/budget mismatch')
            if any(r.get(k)!=v for k,v in parse_output(r['text'],row['content'],finished,head).items()):
                raise ValueError('Source evidence mismatch')
        if read_json(OUT/'decisions.json')!=[resolved_record(row,r) for row,r in zip(rows,raw,strict=True)] or read_json(OUT/'summary.json')!=metrics(raw,rows):
            raise ValueError('Policy/metrics mismatch')
        write_json(OUT/'verification/result.json',{'state':'PASS','records':len(raw)})
    print('New bilingual confirmation verification PASS',flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True,choices=('prepare','run','verify'))
    {'prepare':prepare,'run':run,'verify':verify}[parser.parse_args().stage]()


if __name__=='__main__':
    main()
