"""Offline replay of decisions, source coverage and metrics; no further model inference."""
from pathlib import Path
import math
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.content_probe_v1 import content_segments, parse_decision, summarize, windows

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/bipia/content_probe_v1'
OUT = ROOT / 'results/bipia/content_probe_v1_compat'


def check_identity(items: list[dict], expected: list[dict], arm: str) -> None:
    """Exactly one prediction per ID with source/label binding preserved."""
    lookup = {r['id']:r for r in expected}
    if len(items) != len(lookup) or {r['id'] for r in items} != set(lookup):
        raise ValueError(f'{arm}: missing, duplicated or unexpected IDs')
    for r in items:
        gold = lookup[r['id']]
        if r['source'] != gold['source'] or r['expected'] != gold['expected']:
            raise ValueError(f'{arm}: source/label binding changed')
        if read_json(OUT/arm/'raw'/(r['id']+'.json')) != r:
            raise ValueError(f'{arm}: raw/expanded mismatch')


def replay_classifier(items: list[dict], rows: list[dict], tokenizer, spec: dict) -> None:
    """Check exact window layout, full coverage, probability aggregation and thresholds."""
    lookup = {r['id']:r for r in rows}
    capacity = spec['context'] - tokenizer.num_special_tokens_to_add(pair=False)
    for r in items:
        expected = []
        for index, segment in enumerate(content_segments(lookup[r['id']]['content'])):
            ids = tokenizer(segment,add_special_tokens=False,truncation=False)['input_ids']
            if ids:
                expected.append({'segment':index,'tokens':len(ids),'windows':[list(x) for x in windows(ids,capacity,spec['overlap'])]})
        if r['coverage'] != expected:
            raise ValueError('Classifier token coverage differs')
        layout = [(c['segment'],a,b) for c in expected for a,b in c['windows']]
        if [(s['segment'],s['start'],s['end']) for s in r['window_scores']] != layout:
            raise ValueError('Classifier window scores missing')
        probabilities = [s['risk_probability'] for s in r['window_scores']]
        if not all(math.isfinite(p) and 0 <= p <= 1 for p in probabilities):
            raise ValueError('Invalid probability')
        score = max(probabilities)
        whole = max(s['risk_probability'] for s in r['window_scores'] if s['segment'] == 0)
        if score != r['score'] or whole != r['whole_score']:
            raise ValueError('Aggregation mismatch')
        if r['decision'] != ('RISK' if score >= spec['threshold'] else 'NORMAL'):
            raise ValueError('Classifier threshold changed')


def replay_direct(items: list[dict], rows: list[dict], tokenizer, spec: dict) -> None:
    """Replay saved token output and exact evidence validation without repairing it."""
    import json
    lookup = {r['id']:r for r in rows}
    for r in items:
        row = lookup[r['id']]
        messages = [{'role':'system','content':spec['prompt']},{'role':'user','content':
                    json.dumps({'trusted_user_task':row['task'],'untrusted_external_content':row['content']},ensure_ascii=False)}]
        ids = tokenizer.apply_chat_template(messages,tokenize=True,return_dict=False,
                                            add_generation_prompt=True,enable_thinking=False)
        if ids != r['input_ids'] or len(ids) != r['input_tokens']:
            raise ValueError('Direct input token identity changed')
        if len(ids)+spec['max_new_tokens'] > spec['total_budget']:
            if r['decision'] != 'INVALID' or r['generated_token_ids']:
                raise ValueError('Over-budget input was silently scored')
            continue
        text = tokenizer.decode(r['generated_token_ids'],skip_special_tokens=True)
        finished = bool(r['generated_token_ids']) and r['generated_token_ids'][-1] == tokenizer.eos_token_id
        value = parse_decision(text,row['content'],finished)
        if text != r['text'] or finished != r['finished'] or any(r.get(k) != v for k,v in value.items()):
            raise ValueError('Direct output replay mismatch')


def pair_accuracy(items: list[dict], shared: list[dict]) -> dict:
    """An intact pair succeeds only when both clean and attacked decisions are correct."""
    lookup = {r['id']:r for r in items}
    pairs = {r['pair_id'] for r in shared if r['source'] == 'secopd'}
    correct = sum(lookup[p+'-clean']['decision'] == 'NORMAL' and lookup[p+'-attacked']['decision'] == 'RISK' for p in pairs)
    return {'correct':correct,'n':len(pairs)}


def main() -> None:
    from transformers import AutoTokenizer
    protocol = read_json(DATA/'protocol.json')
    for name,digest in read_json(DATA/'integrity.json').items():
        require_hash(DATA/name,digest)
    for name,digest in protocol['sources_sha256'].items():
        require_hash(ROOT/name,digest)
    for name,digest in protocol['code_sha256'].items():
        require_hash(Path(__file__).with_name(name),digest)
    shared, standalone = read_json(DATA/'shared.json'),read_json(DATA/'standalone.json')
    classifier_rows = list({r['id']:r for r in standalone+[r for r in shared if r['language']=='en']}.values())
    predictions = {}
    artifact_hashes = {}
    for arm in ('classifier','direct'):
        if read_json(OUT/arm/'status.json')['state'] != 'COMPLETE':
            raise ValueError('Inference arm incomplete')
        run = read_json(OUT/arm/'protocol.json')
        require_hash(DATA/'protocol.json',run['data_protocol_sha256'])
        require_hash(Path(__file__).with_name('run_content_probe_v1_compat.py'),run['runtime_sha256'])
        model_path = ROOT/('external/content_classifier_v1' if arm=='classifier' else protocol['direct']['model'])
        for name,digest in run['model_hashes'].items():
            require_hash(model_path/name,digest)
        predictions[arm] = read_json(OUT/arm/'predictions.json')
        if summarize(predictions[arm]) != read_json(OUT/arm/'summary.json'):
            raise ValueError('Saved summary differs from replay')
        artifact_hashes[arm] = file_sha256(OUT/arm/'predictions.json')
    with new_run(OUT/'verification',{'predictions_sha256':artifact_hashes,'verifier_sha256':file_sha256(Path(__file__))}):
        check_identity(predictions['classifier'],classifier_rows,'classifier')
        check_identity(predictions['direct'],shared,'direct')
        tokenizer = AutoTokenizer.from_pretrained(ROOT/'external/content_classifier_v1',local_files_only=True,trust_remote_code=False)
        replay_classifier(predictions['classifier'],classifier_rows,tokenizer,protocol['classifier'])
        tokenizer = AutoTokenizer.from_pretrained(ROOT/protocol['direct']['model'],local_files_only=True,trust_remote_code=False)
        replay_direct(predictions['direct'],shared,tokenizer,protocol['direct'])
        ids = {r['id'] for r in shared if r['language']=='en'}
        common = {arm:summarize([r for r in rows if r['id'] in ids]) for arm,rows in predictions.items()}
        pairs = {arm:pair_accuracy(rows,shared) for arm,rows in predictions.items()}
        frozen = {r['id']:r for r in read_json(ROOT/'results/bipia/baseline_cross_source_v1/decisions.json')}
        selected = [r for r in shared if r['source']=='injecagent']
        baseline = {system:{'flagged':sum(frozen[r['id']][system] != 'ALLOW' for r in selected),'n':len(selected)}
                    for system in ('rule','semantic','hybrid')}
        write_json(OUT/'verification/result.json',{'state':'PASS','classifier_records':len(classifier_rows),
                   'direct_records':len(shared),'common_english':common,'secopd_both_correct':pairs,'frozen_baseline_same_injecagent':baseline,
                   'limitations':'EXPOSED diagnostic; probability/logit inference not rerun; token identity, evidence, score aggregation and metrics replayed'})
    print('Content probe verification PASS',flush=True)


if __name__=='__main__':
    main()
