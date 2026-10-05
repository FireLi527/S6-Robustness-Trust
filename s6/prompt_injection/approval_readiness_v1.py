"""Auditable bounded bilingual extraction of explicit missing prior approval."""
from __future__ import annotations

import hashlib
import re
from s6.prompt_injection.trusted_review_route_v1 import resolve as legacy_resolve


def task_digest(task: str) -> str:
    """Bind a readiness state to the actual trusted task, never external content."""
    if not isinstance(task,str) or not task.strip():
        raise ValueError('Nonempty trusted task required')
    return hashlib.sha256(task.encode('utf-8')).hexdigest()


def visible_task(task: str) -> str:
    """Mask simple quoted spans without moving evidence offsets; not a full parser."""
    task_digest(task)
    return re.sub(r'```[\s\S]*?```|"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|(?<!\w)\x27[^\x27\n]*\x27(?!\w)',lambda m:' '*len(m.group()),task)


def extract_readiness(task: str) -> dict:
    """Extract positive dependency plus explicitly missing evidence from trusted text."""
    text = visible_task(task)
    flags = re.IGNORECASE
    analysis = bool(re.search(r'\b(?:explain|describe|translate|analy[sz]e|summarize)\b|解释|分析|翻译|总结',text,flags))
    no_action = bool(re.search(r'\b(?:do not (?:execute|perform|carry out)|take no action)\b|不执行|不要执行|不得执行|只分析文字',text,flags))
    conditional = bool(re.search(r'\b(?:only|unless|until|after|subject to)\b|只有|仅在|必须先|获批后',text,flags))
    operation = bool(re.search(r'\b(?:perform|execute|proceed|act|apply|run|use|using)\b|执行|运行|进行操作',text,flags))
    dependency = re.search(r'\b(?:previously|earlier|prior|previous)\s+(?:approved|approval)\b|(?:先前|此前|之前)(?:批准|审批)',text,flags)
    missing = re.search(r'\b(?:approval(?:\s+record)?\s+(?:is|was)\s+(?:unavailable|missing|not available)|(?:no access|cannot access|can[’\x27]t access|unable to access)\s+to\s+(?:that|the|my|previous|prior)?\s*approval)\b|(?:无法|不能)(?:查到|获取|访问|查阅|找到)[^。；;\n]{0,20}(?:审批|批准)(?:记录)?',text,flags)
    available = re.search(r'\bapproval(?:\s+record)?\s+(?:is|was)\s+(?:available|present|accessible)\b|审批记录(?:现在|目前|已)?(?:可用|可访问|已找到)',text,flags)
    analysis_only = analysis and no_action
    needed = conditional and operation and dependency is not None and not analysis_only
    absent = needed and missing is not None and available is None
    evidence = []
    for kind,match in [('dependency',dependency),('availability',missing),('counterevidence',available)]:
        if match is not None:
            evidence.append({'kind':kind,'start':match.start(),'end':match.end(),'text':task[match.start():match.end()]})
    return {'schema':'approval-readiness-v1','task_sha256':task_digest(task),
            'mode':'ANALYSIS_ONLY' if analysis_only else 'OPERATION_CONDITIONAL' if needed else 'UNASSESSED',
            'requires_prior_approval':needed,'approval_availability':'EXPLICITLY_MISSING' if absent else 'CONFLICTING' if needed and missing and available else 'UNASSESSED',
            'evidence':evidence,'provenance':'bounded trusted-task pattern extraction; no permission validation'}


def validate_readiness(task: str,state: dict) -> None:
    """Reject stale/tampered states rather than trusting a copied availability flag."""
    if state!=extract_readiness(task):
        raise ValueError('Readiness state differs from bound trusted task extraction')


def resolve_readiness(task: str,component: dict,state: dict | None = None) -> dict:
    """Add review readiness, preserve original head/signal, and authorize no execution."""
    bound = extract_readiness(task) if state is None else state
    validate_readiness(task,bound)
    old = legacy_resolve(task,component)
    missing = bound['requires_prior_approval'] and bound['approval_availability']=='EXPLICITLY_MISSING'
    decision = 'UNKNOWN' if missing else old['decision']
    return {**old,'decision':decision,'approval_readiness':bound,
            'risk_alert':component['decision']=='RISK','review_required':decision in {'UNKNOWN','RISK'},
            'execution_authorized':False,'legacy_decision':old['decision']}
