"""Task-aware reviewer arbitration, with explicit missing-information abstention."""
from __future__ import annotations


def arbitrate(classifier: str,reviewer: str) -> str:
    """Valid task review leads; classifier rescues risk only on invalid review."""
    if classifier not in {'NORMAL','RISK'} or reviewer not in {'NORMAL','RISK','UNKNOWN','INVALID'}:
        raise ValueError('Unexpected component labels')
    if reviewer in {'NORMAL','RISK','UNKNOWN'}:
        return reviewer
    return 'RISK' if classifier=='RISK' else 'UNKNOWN'
