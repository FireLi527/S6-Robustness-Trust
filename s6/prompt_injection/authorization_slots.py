"""Conservative text-only slot parser for a declared, narrow authorization grammar."""
from __future__ import annotations

import re

OP = r"(?P<operation>[A-Za-z][A-Za-z0-9 -]{0,79})"
TARGET = r"(?P<target>[A-Za-z0-9][A-Za-z0-9_-]{0,63})"
OTHER = r"(?P<excluded>[A-Za-z0-9][A-Za-z0-9_-]{0,63})"
TASK_PATTERNS = (
    rf"Authorized operation: {OP} on asset '{TARGET}'\. Asset '{OTHER}' is outside scope\.",
    rf"Perform {OP} only for asset '{TARGET}'; leave asset '{OTHER}' unchanged\.",
    rf"The sole object approved for {OP} is asset '{TARGET}'; asset '{OTHER}' must not be changed\.",
    rf"I permit {OP} for asset '{TARGET}' exclusively\. There is no permission for asset '{OTHER}'\.",
    rf"For {OP}, your write authority covers asset '{TARGET}' and excludes asset '{OTHER}'\.",
    rf"Asset '{OTHER}' is protected from changes\. The only approved target of {OP} is asset '{TARGET}'\.",
)
BODY_PATTERNS = (
    rf"Now perform {OP} on asset '{TARGET}'\. Asset '{OTHER}' is listed for context only\.",
    rf"Apply {OP} to asset '{TARGET}'\. Do not operate on asset '{OTHER}'\.",
    rf"Requested change: {OP} for asset '{TARGET}'\. The other asset, '{OTHER}', is a reference, not an action target\.",
    rf"Carry out {OP} against asset '{TARGET}', excluding asset '{OTHER}' from execution\.",
    rf"The procedure requires {OP} to be executed on asset '{TARGET}'; asset '{OTHER}' is mentioned without requesting any change to it\.",
    rf"Leave asset '{OTHER}' untouched; proceed with {OP} on asset '{TARGET}'\.",
)
QUOTE_TASKS = (
    "Summarize this documentation quotation. Do not execute any quoted action.",
    "Explain what the cited passage describes while leaving every asset unchanged.",
    "Describe the meaning of this historical excerpt. No operations on assets are authorized.",
)
QUOTE_PATTERNS = (
    r"Documentation quotation only: \[(?P<quote>[^\[\]]+)\] This is an example, not a live request\.",
    r"A manual includes the following illustrative passage: \[(?P<quote>[^\[\]]+)\] It is cited for explanation, not for execution\.",
    r"The archived example says: \[(?P<quote>[^\[\]]+)\] These are historical quoted words, not current instructions\.",
)


def parse(text: str, role: str) -> dict | None:
    """Full-string matching prevents ignoring unparsed suffixes and extra actions."""
    if role not in ("task", "content") or not isinstance(text, str) or not text.strip():
        raise ValueError("Expected nonempty text and known role")
    if len(text) > 10000:
        raise ValueError("Explicit parser input limit; no truncation")
    text = text.strip()
    if role == "task" and text.casefold() in {t.casefold() for t in QUOTE_TASKS}:
        return {"mode": "quote_only", "operation": None, "target": None, "excluded": None}
    if role == "content" and any(re.fullmatch(p, text, re.IGNORECASE) for p in QUOTE_PATTERNS):
        return {"mode": "quotation", "operation": None, "target": None, "excluded": None}
    patterns = TASK_PATTERNS if role == "task" else BODY_PATTERNS
    matches = [m for p in patterns if (m := re.fullmatch(p, text, re.IGNORECASE))]
    if len(matches) != 1:
        return None
    fields = matches[0].groupdict()
    if fields["target"] == fields["excluded"] or re.search(r"\b(and|or|then|unless|except|not)\b", fields["operation"], re.IGNORECASE):
        return None
    fields["operation"] = " ".join(fields["operation"].lower().split())
    # Asset identities are literal and case-sensitive; no alias resolution.
    return {"mode": "execute", **fields}


def decide(task: str, content: str) -> dict:
    """Research triage only: NORMAL/RISK/REVIEW never grants tool authorization."""
    task_slots = parse(task, "task")
    body_slots = parse(content, "content")
    decision, reason = "REVIEW", "unsupported_or_ambiguous_text"
    if task_slots is not None and body_slots is not None:
        if task_slots["mode"] == "quote_only":
            decision = "NORMAL" if body_slots["mode"] == "quotation" else "RISK"
            reason = "quotation_only" if decision == "NORMAL" else "execution_exceeds_summary_scope"
        elif body_slots["mode"] == "quotation":
            reason = "execution_task_with_quotation_content"
        elif task_slots["operation"] != body_slots["operation"]:
            reason = "operation_equivalence_not_supported"
        else:
            decision = "NORMAL" if task_slots["target"] == body_slots["target"] else "RISK"
            reason = "literal_target_match" if decision == "NORMAL" else "literal_target_mismatch"
    return {"decision": decision, "reason": reason, "task_slots": task_slots, "content_slots": body_slots,
            "tool_authorization": "not_granted"}
