"""Pinned user-downloaded Prompt Guard 2 on the existing exposed diagnostic cohorts."""
from __future__ import annotations

import argparse
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.content_probe_v1 import summarize
from s6.prompt_injection.run_content_probe_v1_compat import inputs, scan_classifier
from s6.prompt_injection.verify_content_probe_v1 import replay_classifier, pair_accuracy

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'external/llama_prompt_guard_2_22m'
SNAPSHOT = ROOT / 'data/bipia/prompt_guard_2_snapshot_v1'
OUT = ROOT / 'results/bipia/prompt_guard_2_v1'


def diagnostic_rows() -> tuple[list[dict], list[dict], dict]:
    """Exactly the previous 1473 English records plus 12 separate synthetic controls."""
    shared, standalone, parent = inputs()
    rows = list({r['id']:r for r in standalone+[r for r in shared if r['language']=='en']}.values())
    controls_path = ROOT/'results/bipia/content_controls_v1/inputs.json'
    controls = read_json(controls_path)
    require_hash(controls_path,read_json(ROOT/'results/bipia/content_controls_v1/verification/protocol.json')['inputs_sha256'])
    if len(rows)!=1473 or len(controls)!=12:
        raise ValueError('Previous diagnostic coverage changed')
    return rows+controls, shared, parent


def verify_snapshot() -> dict:
    """Local downloaded files stay unchanged; identity and hashes live in a separate snapshot."""
    if read_json(SNAPSHOT/'status.json')['state']!='COMPLETE':
        raise ValueError('Model snapshot incomplete')
    hashes = read_json(SNAPSHOT/'files_sha256.json')
    for name,digest in hashes.items():
        require_hash(MODEL/name,digest)
    return hashes


def run() -> None:
    """Freeze the same threshold and scanning method before any model scoring."""
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    rows,shared,parent = diagnostic_rows()
    hashes = verify_snapshot()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no silent fallback')
    spec = {**parent['classifier'],'repo':'meta-llama/Llama-Prompt-Guard-2-22M',
            'revision':read_json(SNAPSHOT/'protocol.json')['revision'],'risk_class_index':1,
            'temperature':1.0,'label_reference':'https://github.com/meta-llama/llama-cookbook/blob/main/getting-started/responsible_ai/prompt_guard/inference.py'}
    protocol = {'purpose':'EXPOSED diagnostic, new model only; no threshold tuning, no training or deployment',
                'spec':spec,'model_hashes':hashes,'snapshot_sha256':file_sha256(SNAPSHOT/'files_sha256.json'),
                'data_protocol_sha256':file_sha256(ROOT/'data/bipia/content_probe_v1/protocol.json'),
                'controls_sha256':file_sha256(ROOT/'results/bipia/content_controls_v1/inputs.json'),
                'code_sha256':{name:file_sha256(Path(__file__).with_name(name)) for name in
                               ('evaluate_prompt_guard_2_v1.py','content_probe_v1.py','run_content_probe_v1_compat.py','verify_content_probe_v1.py')}}
    with new_run(OUT,protocol):
        tokenizer = AutoTokenizer.from_pretrained(MODEL,local_files_only=True,trust_remote_code=False)
        ids = tokenizer('tokenizer compatibility check',add_special_tokens=False)['input_ids']
        if tokenizer('tokenizer compatibility check')['input_ids'] != [tokenizer.cls_token_id]+ids+[tokenizer.sep_token_id]:
            raise ValueError('Special-token layout incompatible')
        model = AutoModelForSequenceClassification.from_pretrained(MODEL,local_files_only=True,trust_remote_code=False).to('cuda').eval()
        if model.config.num_labels!=2 or model.config.max_position_embeddings!=512:
            raise ValueError('Unexpected binary classifier architecture')
        results = []
        for index,row in enumerate(rows,1):
            record = {k:row[k] for k in ('id','source','expected')}
            record.update(scan_classifier(model,tokenizer,row['content'],'cuda',spec))
            write_json(OUT/'raw'/(row['id']+'.json'),record)
            results.append(record)
            if index%50==0:
                print(f'Prompt Guard 2 {index}/{len(rows)}',flush=True)
        write_json(OUT/'predictions.json',results)
        write_json(OUT/'summary.json',summarize(results))
        write_json(OUT/'whole_summary.json',summarize([{**r,'decision':r['whole_decision']} for r in results]))
        common_ids = {r['id'] for r in shared if r['language']=='en'}
        write_json(OUT/'common_summary.json',summarize([r for r in results if r['id'] in common_ids]))
        write_json(OUT/'secopd_paired.json',pair_accuracy(results,shared))
        controls = {r['id']:r for r in results if r['source']=='task_swap'}
        groups = {r['group_id'] for r in rows if r['source']=='task_swap'}
        both = sum(controls['control-'+g+'-authorized']['decision']=='NORMAL' and
                   controls['control-'+g+'-unauthorized']['decision']=='RISK' for g in groups)
        write_json(OUT/'controls_paired.json',{'both_correct':both,'groups':len(groups),'synthetic_human_reviewed':False})
    print('Prompt Guard 2 evaluation COMPLETE',flush=True)


def verify() -> None:
    """Replay raw records, coverage, scores, model/code identity and all source metrics."""
    from transformers import AutoTokenizer
    if read_json(OUT/'status.json')['state']!='COMPLETE':
        raise ValueError('Evaluation incomplete')
    protocol = read_json(OUT/'protocol.json')
    rows,shared,_ = diagnostic_rows()
    hashes = verify_snapshot()
    if hashes!=protocol['model_hashes']:
        raise ValueError('Model identity changed')
    require_hash(SNAPSHOT/'files_sha256.json',protocol['snapshot_sha256'])
    for name,digest in protocol['code_sha256'].items():
        require_hash(Path(__file__).with_name(name),digest)
    require_hash(ROOT/'data/bipia/content_probe_v1/protocol.json',protocol['data_protocol_sha256'])
    require_hash(ROOT/'results/bipia/content_controls_v1/inputs.json',protocol['controls_sha256'])
    results = read_json(OUT/'predictions.json')
    lookup = {r['id']:r for r in rows}
    with new_run(OUT/'verification',{'predictions_sha256':file_sha256(OUT/'predictions.json'),'verifier_sha256':file_sha256(Path(__file__))}):
        if len(results)!=len(lookup) or {r['id'] for r in results}!=set(lookup):
            raise ValueError('Prediction ID coverage changed')
        for r in results:
            if r['source']!=lookup[r['id']]['source'] or r['expected']!=lookup[r['id']]['expected']:
                raise ValueError('Label/source identity changed')
            if read_json(OUT/'raw'/(r['id']+'.json'))!=r:
                raise ValueError('Raw/expanded mismatch')
        tokenizer = AutoTokenizer.from_pretrained(MODEL,local_files_only=True,trust_remote_code=False)
        replay_classifier(results,rows,tokenizer,protocol['spec'])
        if summarize(results)!=read_json(OUT/'summary.json'):
            raise ValueError('Summary replay mismatch')
        whole = [{**r,'decision':r['whole_decision']} for r in results]
        if summarize(whole)!=read_json(OUT/'whole_summary.json'):
            raise ValueError('Whole-carrier summary mismatch')
        ids = {r['id'] for r in shared if r['language']=='en'}
        if summarize([r for r in results if r['id'] in ids])!=read_json(OUT/'common_summary.json'):
            raise ValueError('Common-cohort summary mismatch')
        if pair_accuracy(results,shared)!=read_json(OUT/'secopd_paired.json'):
            raise ValueError('Paired summary mismatch')
        controls = {r['id']:r for r in results if r['source']=='task_swap'}
        groups = {r['group_id'] for r in rows if r['source']=='task_swap'}
        both = sum(controls['control-'+g+'-authorized']['decision']=='NORMAL' and
                   controls['control-'+g+'-unauthorized']['decision']=='RISK' for g in groups)
        if read_json(OUT/'controls_paired.json')!={'both_correct':both,'groups':len(groups),'synthetic_human_reviewed':False}:
            raise ValueError('Synthetic control summary mismatch')
        write_json(OUT/'verification/result.json',{'state':'PASS','records':len(results),'primary_records':1473,'synthetic_controls':12,
                   'limits':'No logits reinference; token coverage, max aggregation, decisions and metrics replayed'})
    print('Prompt Guard 2 verification PASS',flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    if parser.parse_args().verify:
        verify()
    else:
        run()


if __name__=='__main__':
    main()
