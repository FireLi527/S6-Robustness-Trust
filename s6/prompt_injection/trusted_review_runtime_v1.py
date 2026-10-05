"""Fresh routed inference using the frozen task grammar and evidence heads."""
from __future__ import annotations

from s6.prompt_injection.reviewer_ablation_v1 import infer_batch
from s6.prompt_injection.trusted_review_route_v1 import task_profile, resolve


def routed_batches(rows: list[dict]) -> list[tuple[str,list[dict]]]:
    """Group by trusted-task head, preserving source order within each head."""
    if not rows or len({r['id'] for r in rows})!=len(rows):
        raise ValueError('Nonempty unique input IDs required')
    groups = {head:[] for head in ('evidence_only','both')}
    for row in rows:
        groups[task_profile(row['task'])['head']].append(row)
    return [(head,group[start:start+4]) for head,group in groups.items()
            for start in range(0,len(group),4)]


def resolved_record(row: dict,component: dict) -> dict:
    """Keep policy readiness separate from model output and inference latency."""
    head = task_profile(row['task'])['head']
    if component['id']!=row['id'] or component['arm']!=head:
        raise ValueError('Input/head identity mismatch')
    return {**{k:row[k] for k in ('id','source','expected')},
            **resolve(row['task'],component),'seconds':component['seconds']}


def infer_routed_batch(model,tokenizer,rows: list[dict],head: str,spec: dict) -> list[dict]:
    """One fresh greedy batch; no cache, repairs, retries or authorization grant."""
    if any(task_profile(r['task'])['head']!=head for r in rows):
        raise ValueError('Routed batch contains a different trusted-task head')
    return infer_batch(model,tokenizer,rows,head,spec)
