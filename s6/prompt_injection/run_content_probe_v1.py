"""Offline, immutable classifier and base-Qwen direct decision diagnostic arms."""
from __future__ import annotations

import argparse
from pathlib import Path
import time
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.content_probe_v1 import content_segments, parse_decision, summarize, windows

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/bipia/content_probe_v1'
OUT = ROOT / 'results/bipia/content_probe_v1'


def inputs() -> tuple[list[dict], list[dict], dict]:
    """Verify input and code identity before inference; labels never enter model prompts."""
    protocol = read_json(DATA / 'protocol.json')
    if read_json(DATA / 'status.json')['state'] != 'COMPLETE':
        raise ValueError('Protocol incomplete')
    for name, digest in read_json(DATA / 'integrity.json').items():
        require_hash(DATA / name, digest)
    for name, digest in protocol['sources_sha256'].items():
        require_hash(ROOT / name, digest)
    for name, digest in protocol['code_sha256'].items():
        require_hash(Path(__file__).with_name(name), digest)
    return read_json(DATA / 'shared.json'), read_json(DATA / 'standalone.json'), protocol


def verify_model(path: Path) -> dict:
    """Include every frozen weight/tokenizer file in the run identity."""
    if read_json(path / 'status.json')['state'] != 'COMPLETE':
        raise ValueError('Model download incomplete')
    hashes = read_json(path / 'files_sha256.json')
    if 'files' in hashes:
        hashes = hashes['files']
    for name, digest in hashes.items():
        require_hash(path / name, digest)
    return hashes


def scan_classifier(model, tokenizer, content: str, device: str, spec: dict) -> dict:
    """Record full token coverage and compare whole-carrier vs segmented scores."""
    import torch
    started = time.perf_counter()
    segments, features, coverage = content_segments(content), [], []
    capacity = spec['context'] - tokenizer.num_special_tokens_to_add(pair=False)
    for index, segment in enumerate(segments):
        ids = tokenizer(segment, add_special_tokens=False, truncation=False)['input_ids']
        if not ids:
            continue
        spans = windows(ids, capacity, spec['overlap'])
        coverage.append({'segment': index, 'tokens': len(ids), 'windows': spans})
        for start, end in spans:
            feature = tokenizer.prepare_for_model(ids[start:end], add_special_tokens=True,
                                                   return_attention_mask=True, truncation=False)
            if len(feature['input_ids']) > spec['context']:
                raise ValueError('Classifier window exceeded model budget')
            features.append((index, start, end, feature))
    if len(features) > 512:
        raise ValueError('Explicit classifier resource boundary: >512 windows')
    scores = []
    with torch.inference_mode():
        for start in range(0, len(features), 16):
            batch = tokenizer.pad([f[3] for f in features[start:start+16]], padding=True, return_tensors='pt').to(device)
            probabilities = torch.softmax(model(**batch).logits.float(), dim=-1)[:, 1].cpu().tolist()
            scores.extend({'segment': f[0], 'start': f[1], 'end': f[2], 'risk_probability': p}
                          for f, p in zip(features[start:start+16], probabilities, strict=True))
    if not scores:
        raise ValueError('Empty classifier content')
    whole = max(s['risk_probability'] for s in scores if s['segment'] == 0)
    score = max(s['risk_probability'] for s in scores)
    return {'decision': 'RISK' if score >= spec['threshold'] else 'NORMAL', 'score': score,
            'whole_score': whole, 'whole_decision': 'RISK' if whole >= spec['threshold'] else 'NORMAL',
            'coverage': coverage, 'window_scores': scores, 'seconds': time.perf_counter()-started, 'valid': True}


def classifier(shared: list[dict], standalone: list[dict], protocol: dict) -> None:
    """English-only classifier, evaluated on full external diagnostic and shared subset."""
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    path = ROOT / 'external/content_classifier_v1'
    model_hashes = verify_model(path)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no silent runtime fallback')
    device = 'cuda'
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True, trust_remote_code=False).to(device).eval()
    if model.config.num_labels != 2 or model.config.id2label[1].upper() != 'INJECTION':
        raise ValueError(f'Unexpected classifier label mapping: {model.config.id2label}')
    rows = list({r['id']: r for r in standalone + [r for r in shared if r['language'] == 'en']}.values())
    with new_run(OUT / 'classifier', {'data_protocol_sha256': file_sha256(DATA/'protocol.json'),
                                    'spec': protocol['classifier'], 'model_hashes': model_hashes}):
        items = []
        for index, row in enumerate(rows, 1):
            result = scan_classifier(model, tokenizer, row['content'], device, protocol['classifier'])
            record = {k: row[k] for k in ('id','source','expected')}
            record.update(result)
            write_json(OUT / 'classifier/raw' / (row['id']+'.json'), record)
            items.append(record)
            if index % 20 == 0:
                print(f'Classifier {index}/{len(rows)}', flush=True)
        write_json(OUT/'classifier/predictions.json', items)
        write_json(OUT/'classifier/summary.json', summarize(items))
        write_json(OUT/'classifier/whole_summary.json', summarize([{**r,'decision':r['whole_decision']} for r in items]))


def direct(shared: list[dict], protocol: dict) -> None:
    """Base model only, task-conditioned decisions without adapters or generated permissions."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    spec = protocol['direct']
    path = ROOT / spec['model']
    model_hashes = verify_model(path)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=torch.bfloat16)
    with new_run(OUT/'direct', {'data_protocol_sha256':file_sha256(DATA/'protocol.json'), 'spec':spec, 'model_hashes':model_hashes}):
        model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                                   quantization_config=config, device_map={'':0}, dtype=torch.bfloat16,
                                                   attn_implementation='sdpa').eval()
        model.requires_grad_(False)
        items = []
        for index, row in enumerate(shared, 1):
            import json
            messages = [{'role':'system','content':spec['prompt']}, {'role':'user','content':
                         json.dumps({'trusted_user_task':row['task'],'untrusted_external_content':row['content']},ensure_ascii=False)}]
            ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)
            record = {k:row[k] for k in ('id','source','expected')}
            record.update({'input_tokens':len(ids),'input_ids':ids})
            started = time.perf_counter()
            if len(ids)+spec['max_new_tokens'] > spec['total_budget']:
                record.update({'decision':'INVALID','valid':False,'error':'Complete input exceeds explicit token budget',
                               'text':'','generated_token_ids':[],'finished':False})
            else:
                inputs_tensor = torch.tensor([ids],device='cuda')
                with torch.inference_mode():
                    output = model.generate(input_ids=inputs_tensor, attention_mask=torch.ones_like(inputs_tensor),
                                            max_new_tokens=spec['max_new_tokens'], do_sample=False,
                                            pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id)
                generated = output[0,len(ids):].tolist()
                text = tokenizer.decode(generated,skip_special_tokens=True)
                finished = bool(generated) and generated[-1] == tokenizer.eos_token_id
                record.update({'text':text,'generated_token_ids':generated,'finished':finished,
                               **parse_decision(text,row['content'],finished)})
            record['seconds'] = time.perf_counter()-started
            write_json(OUT/'direct/raw'/(row['id']+'.json'),record)
            items.append(record)
            print(f'Direct {index}/{len(shared)} {row["id"]} {record["decision"]}',flush=True)
        write_json(OUT/'direct/predictions.json',items)
        write_json(OUT/'direct/summary.json',summarize(items))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',required=True,choices=('classifier','direct'))
    arm = parser.parse_args().arm
    shared, standalone, protocol = inputs()
    if arm == 'classifier':
        classifier(shared, standalone, protocol)
    else:
        direct(shared, protocol)


if __name__ == '__main__':
    main()
