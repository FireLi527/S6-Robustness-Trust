"""Small trusted-task routing grammar and explicit missing-approval review state."""
from __future__ import annotations

import re


def task_profile(task: str) -> dict:
    """Only trusted task text enters routing; source metadata and labels cannot steer it."""
    if not isinstance(task,str) or not task.strip():
        raise ValueError('Explicit trusted task required')
    text = task.casefold()
    quoted = (bool(re.search(r'\bquoted\b',text)) and
              bool(re.search(r'\b(?:explain|translate|analy[sz]e)\b',text)) and
              bool(re.search(r'\bdo not\s+(?:perform|execute|carry out)\b',text)))
    missing = (not quoted and bool(re.search(r'\b(?:perform|execute|act|proceed)\b',text)) and
               bool(re.search(r'\bonly\b',text)) and
               bool(re.search(r'\b(?:previous|prior)\s+approval\s+record\s+(?:is|was)\s+(?:unavailable|missing|not\s+available)\b',text)))
    explicit = bool(re.search(r'\bi\s+(?:explicitly\s+)?authorize\b',text))
    return {'head':'both' if quoted or missing or explicit else 'evidence_only',
            'quote_analysis':quoted,'explicit_authorization_statement':explicit,
            'declared_approval_missing':missing,'grammar':'narrow explicit English; otherwise default evidence reviewer'}


def resolve(task: str,component: dict) -> dict:
    """Keep model risk signal distinct from authorizing an operation; grant nothing."""
    profile = task_profile(task)
    signal = component['decision']
    if signal not in {'NORMAL','RISK','UNKNOWN','INVALID'}:
        raise ValueError('Unexpected model risk signal')
    if profile['declared_approval_missing']:
        decision,scope = 'UNKNOWN','EXPLICITLY_MISSING'
    else:
        decision,scope = ('UNKNOWN' if signal=='INVALID' else signal),'UNASSESSED'
    return {'decision':decision,'model_decision':signal,'authority_state':scope,
            'execution_authorized':False,'profile':profile}
