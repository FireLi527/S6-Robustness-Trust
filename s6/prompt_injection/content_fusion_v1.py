"""Explicit decision fusion with abstention; no classifier can grant capabilities."""
from __future__ import annotations

LABELS = {'NORMAL', 'RISK', 'UNKNOWN', 'INVALID'}


def fuse_decisions(classifier: str, reviewer: str, rule: str) -> str:
    """Preserve reviewer failures and distinguish broad detection from consensus."""
    if classifier not in LABELS or reviewer not in LABELS:
        raise ValueError('Unexpected component decision')
    if rule == 'union':
        if 'RISK' in (classifier, reviewer):
            return 'RISK'
        return 'NORMAL' if classifier == reviewer == 'NORMAL' else 'UNKNOWN'
    if rule == 'consensus':
        return classifier if classifier == reviewer and classifier in {'NORMAL', 'RISK'} else 'UNKNOWN'
    raise ValueError('Unsupported fusion rule')
