"""Expanded availability syntax and conservative bilingual analysis intent."""
from __future__ import annotations

import re
from s6.prompt_injection.approval_readiness_v1 import extract_readiness as extract_v1,visible_task
from s6.prompt_injection.trusted_review_route_v1 import task_profile as profile_v1,resolve as resolve_v1


def analysis_intent(task: str) -> dict:
    """Require explicit textual analysis and no action; reject mixed action clauses."""
    text = visible_task(task)
    flags = re.IGNORECASE
    analysis = re.search(r'\b(?:explain|describe|translate|analy[sz]e|summarize)\b|解释|分析|翻译|总结|只说明',text,flags)
    no_action = re.search(r'\b(?:do not (?:execute|perform|carry out)|take no action|no actual action)\b|不执行|不要执行|不得执行|实际操作一律不做|不实际操作|只分析文字',text,flags)
    object_text = re.search(r'\b(?:quoted|quotation|text|note|request|command|step)\b|引用|文字|文本|外部.{0,8}说明',text,flags)
    mixed = re.search(r'\b(?:then|afterwards)\s+(?:execute|perform|send|delete|upload|apply|run)\b|(?:然后|随后|接着)[^。；;\n]{0,8}(?:执行|发送|删除|修改|运行)',text,flags)
    return {'analysis_only':bool(analysis and no_action and object_text and not mixed),
            'mixed_action':bool(mixed),'evidence':[{'kind':kind,'start':m.start(),'end':m.end(),'text':task[m.start():m.end()]}
             for kind,m in [('analysis',analysis),('no_action',no_action),('object',object_text),('mixed_action',mixed)] if m]}


def extract_readiness(task: str) -> dict:
    """Keep v1 evidence; extend grammatical access, absent records and lost approval."""
    base = extract_v1(task)
    text = visible_task(task)
    flags = re.IGNORECASE
    intent = analysis_intent(task)
    missing = re.search(r'\b(?:(?:cannot access|can[’\x27]t access|unable to access)\s+(?:to\s+)?(?:that\s+|the\s+|my\s+|previous\s+|prior\s+)*approval|no\s+(?:saved\s+|available\s+|accessible\s+|existing\s+)?record\s+(?:of|for)\s+(?:my\s+|the\s+|that\s+)?approval|approval(?:\s+record)?\s+(?:is|was|has been)\s+(?:lost|not saved|not retained))\b|(?:审批(?:凭据|记录)|先前批示|批准记录)(?:已经|已|暂时|现在|目前)?(?:丢失|遗失|缺失|不存在|未保存|没有保存)',text,flags)
    needed = base['requires_prior_approval'] and not intent['analysis_only']
    evidence = list(base['evidence'])
    if missing:
        evidence.append({'kind':'availability_v2','start':missing.start(),'end':missing.end(),'text':task[missing.start():missing.end()]})
    counter = any(e['kind']=='counterevidence' for e in evidence)
    absence = base['approval_availability']=='EXPLICITLY_MISSING' or missing is not None
    availability = ('CONFLICTING' if counter and absence else 'EXPLICITLY_MISSING' if absence else 'UNASSESSED') if needed else 'UNASSESSED'
    return {**base,'schema':'approval-readiness-v2','mode':'ANALYSIS_ONLY' if intent['analysis_only'] else 'OPERATION_CONDITIONAL' if needed else 'UNASSESSED',
            'requires_prior_approval':needed,'approval_availability':availability,'evidence':evidence,
            'analysis_intent':intent,'provenance':'bounded bilingual trusted-task extraction; no approval certificate'}


def task_profile(task: str) -> dict:
    """Only explicit analysis-only tasks gain the refined head; other heads stay v1."""
    old = profile_v1(task)
    intent = analysis_intent(task)
    return {**old,'head':'both' if intent['analysis_only'] else old['head'],
            'bilingual_analysis_only':intent['analysis_only'],'intent_evidence':intent['evidence']}


def resolve_readiness(task: str,component: dict,state: dict | None = None) -> dict:
    """No policy shortcut to NORMAL; that label must come from the selected model."""
    bound = extract_readiness(task) if state is None else state
    if bound!=extract_readiness(task):
        raise ValueError('Readiness state differs from current trusted task')
    old = resolve_v1(task,component)
    signal = component['decision']
    missing = bound['requires_prior_approval'] and bound['approval_availability']=='EXPLICITLY_MISSING'
    decision = 'UNKNOWN' if missing else 'UNKNOWN' if signal=='INVALID' else signal
    return {**old,'profile':task_profile(task),'decision':decision,'approval_readiness':bound,
            'risk_alert':signal=='RISK','review_required':decision in {'UNKNOWN','RISK'},
            'execution_authorized':False,'legacy_decision':old['decision']}
