"""Offline batched base-model task/content decisions with complete token accounting."""
from __future__ import annotations

import json
import time
from s6.prompt_injection.content_probe_v1 import parse_decision


def review_batch(model, tokenizer, rows: list[dict], spec: dict) -> list[dict]:
    """Greedy left-padded batch; never repair evidence or silently truncate inputs."""
    import torch
    if not rows or len(rows) > 4:
        raise ValueError('Explicit batch limit is four nonempty records')
    sequences, results, eligible = [], [], []
    for index, row in enumerate(rows):
        if not isinstance(row['task'], str) or not row['task'].strip():
            raise ValueError('Trusted task must be explicit; never infer it from labels')
        messages = [{'role':'system','content':spec['prompt']}, {'role':'user','content':json.dumps(
            {'trusted_user_task':row['task'],'untrusted_external_content':row['content']}, ensure_ascii=False)}]
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                             enable_thinking=False, return_dict=False)
        record = {k:row[k] for k in ('id','source','expected')}
        record.update({'input_ids':ids,'input_tokens':len(ids)})
        if len(ids)+spec['max_new_tokens'] > spec['total_budget']:
            record.update({'decision':'INVALID','valid':False,'error':'Complete input exceeds explicit token budget',
                           'text':'','generated_token_ids':[],'finished':False,'seconds':0.0})
        else:
            eligible.append(index)
            sequences.append(ids)
        results.append(record)
    if not eligible:
        return results
    width = max(map(len,sequences))
    tokens = torch.tensor([[tokenizer.eos_token_id]*(width-len(ids))+ids for ids in sequences],device='cuda')
    mask = torch.tensor([[0]*(width-len(ids))+[1]*len(ids) for ids in sequences],device='cuda')
    started = time.perf_counter()
    with torch.inference_mode():
        outputs = model.generate(input_ids=tokens,attention_mask=mask,max_new_tokens=spec['max_new_tokens'],
                                 do_sample=False,pad_token_id=tokenizer.eos_token_id,eos_token_id=tokenizer.eos_token_id)
    seconds = time.perf_counter()-started
    for batch_index, row_index in enumerate(eligible):
        generated = outputs[batch_index,width:].tolist()
        if tokenizer.eos_token_id in generated:
            generated = generated[:generated.index(tokenizer.eos_token_id)+1]
        text = tokenizer.decode(generated,skip_special_tokens=True)
        finished = bool(generated) and generated[-1] == tokenizer.eos_token_id
        results[row_index].update({'text':text,'generated_token_ids':generated,'finished':finished,
            'batch_seconds':seconds,'seconds':seconds/len(eligible),**parse_decision(text,rows[row_index]['content'],finished)})
    return results
