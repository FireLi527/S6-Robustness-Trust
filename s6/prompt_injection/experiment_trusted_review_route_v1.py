"""Post-hoc routed replay of verified original-evidence and initial-refined heads."""
from __future__ import annotations

import argparse
from pathlib import Path
from s6.engineering.artifacts import file_sha256,new_run,read_json,require_hash,write_json
from s6.prompt_injection.content_probe_v1 import summarize
from s6.prompt_injection.reviewer_ablation_v1 import messages_for,parse_output
from s6.prompt_injection.trusted_review_route_v1 import task_profile,resolve

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'results/bipia/trusted_review_route_v1'


def cache_inputs() -> tuple[list[dict],dict,dict]:
    """Fixed earliest-cache precedence; never choose an output by correctness or score."""
    data = ROOT/'data/bipia/reviewer_refinement_v2'
    require_hash(data/'rows.json',read_json(data/'integrity.json')['rows.json'])
    rows = read_json(data/'rows.json')
    parents = [ROOT/'results/bipia/reviewer_ablation_v1',ROOT/'results/bipia/reviewer_pressure_v2',ROOT/'results/bipia/reviewer_confirmation_v1']
    for p in parents:
        if read_json(p/'verification/result.json')['state']!='PASS':
            raise ValueError('Cached component verification missing')
    jobs = [('evidence_only',parents[0]/'evidence_only/predictions.json'),
            ('both',parents[0]/'both/predictions.json'),('both',parents[1]/'predictions.json'),
            ('both',parents[2]/'both/predictions.json')]
    caches = {'evidence_only':{},'both':{}}
    sources = {data.relative_to(ROOT).as_posix()+'/rows.json':file_sha256(data/'rows.json')}
    for head,path in jobs:
        sources[path.relative_to(ROOT).as_posix()] = file_sha256(path)
        for r in read_json(path):
            caches[head].setdefault(r['id'],r)
    hashes = read_json(parents[0]/'protocol.json')['model_hashes']
    if any(read_json(p/'protocol.json')['model_hashes']!=hashes for p in parents[1:]):
        raise ValueError('Component model identities differ')
    return rows,caches,{'sources_sha256':sources,'model_hashes':hashes}


def replay(rows: list[dict],caches: dict) -> list[dict]:
    result = []
    for row in rows:
        head = task_profile(row['task'])['head']
        r = caches[head].get(row['id'])
        if r is None or r['source']!=row['source'] or r['expected']!=row['expected'] or r['arm']!=head:
            raise ValueError('Matched task-head cache coverage missing')
        result.append({**{k:row[k] for k in ('id','source','expected')},**resolve(row['task'],r)})
    return result


def metrics(records: list[dict],rows: list[dict]) -> dict:
    lookup = {r['id']:r for r in records}
    confirm = [r for r in rows if r.get('human_reviewed',False)]
    groups = {r['group_id'] for r in confirm}
    return {'resolved':summarize(records),'model_signals':summarize([{**r,'decision':r['model_decision']} for r in records]),
            'controlled_all_four_correct':{'hits':sum(all(lookup[r['id']]['decision']==r['expected'] for r in confirm if r['group_id']==g) for g in groups),'n':len(groups)}}


def run() -> None:
    rows,caches,identity = cache_inputs()
    p = {**identity,'purpose':'POST-HOC development cache replay, not live inference, blind test or victim-agent ASR',
         'routing':'Trusted task only: explicit no-execution quoted analysis or first-person authorization uses initial refined ID head; other tasks original ID head',
         'missing_scope':'Explicit English previous-approval-unavailable conditional task -> UNKNOWN readiness; raw model risk signal retained. Not inferred field gold or general missing-scope detector.',
         'cache_precedence':'earliest ablation records first; full pressure only adds missing ids; confirmation adds new ids; no correctness-based selection',
         'code_sha256':{n:file_sha256(Path(__file__).with_name(n)) for n in ('trusted_review_route_v1.py','experiment_trusted_review_route_v1.py','reviewer_ablation_v1.py','content_probe_v1.py')}}
    with new_run(OUT,p):
        records = replay(rows,caches)
        write_json(OUT/'decisions.json',records)
        write_json(OUT/'summary.json',metrics(records,rows))


def verify() -> None:
    from transformers import AutoTokenizer
    if read_json(OUT/'status.json')['state']!='COMPLETE':
        raise ValueError('Route replay incomplete')
    p = read_json(OUT/'protocol.json')
    for name,digest in p['sources_sha256'].items():
        require_hash(ROOT/name,digest)
    for name,digest in p['code_sha256'].items():
        require_hash(Path(__file__).with_name(name),digest)
    model = ROOT/'external/qwen3_4b_train_v1'
    for name,digest in p['model_hashes'].items():
        require_hash(model/name,digest)
    t = AutoTokenizer.from_pretrained(model,local_files_only=True,trust_remote_code=False)
    rows,caches,identity = cache_inputs()
    if identity['model_hashes']!=p['model_hashes']:
        raise ValueError('Matched cache model changed')
    with new_run(OUT/'verification',{'limits':'Selected cache input/output/evidence and policy replay; no fresh integrated inference, no semantic evidence certification'}):
        for row in rows:
            head = task_profile(row['task'])['head']
            r = caches[head][row['id']]
            ids = t.apply_chat_template(messages_for(row,head),tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
            if r['input_ids']!=ids or r['input_tokens']!=len(ids) or t.decode(r['generated_token_ids'],skip_special_tokens=True)!=r['text']:
                raise ValueError('Cached complete input or decode mismatch')
            finished = bool(r['generated_token_ids']) and r['generated_token_ids'][-1]==t.eos_token_id
            if r['finished']!=finished:
                raise ValueError('EOS mismatch')
            parsed = parse_output(r['text'],row['content'],finished,head)
            if any(r.get(k)!=v for k,v in parsed.items()):
                raise ValueError('Cached source evidence mismatch')
        records = replay(rows,caches)
        if records!=read_json(OUT/'decisions.json') or metrics(records,rows)!=read_json(OUT/'summary.json'):
            raise ValueError('Policy/metric replay mismatch')
        write_json(OUT/'verification/result.json',{'state':'PASS','records':len(records),'fresh_model_inferences':0})
    print('Trusted route replay verification PASS',flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',required=True,choices=('run','verify'))
    {'run':run,'verify':verify}[parser.parse_args().stage]()


if __name__=='__main__':
    main()
