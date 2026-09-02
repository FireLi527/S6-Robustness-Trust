"""S6 Milestone P3 — action and permission containment.

Research question (`s6/BASELINE_ROADMAP.md`, Milestone P3): if an injection is missed,
can least privilege prevent it from causing real harm? P1 (`detector.py`) and P2
(`semantic_detector.py`) inspect untrusted *content*; this module inspects the
*action* an agent is about to take as a result of that content, independent of
whether the content looked suspicious.

`evaluate_tool_call` is intentionally blind to ground truth, the same way
`semantic_detector.py`'s `assess_task_consistency` never receives BIPIA's attack
label: its only inputs are a structured `ToolCall` and the content detector's own
live decision. Whether a given call was actually triggered by an attacker, and
whether it would actually cause harm, are unknowable to a real deputy at decision
time and are therefore never passed in here — that ground truth is read only by
`evaluate_tool_policy.py`, and only after this function has already returned a
frozen `ToolPolicyResult` (mirrors the D1 blind-evaluation convention in
`s6/data_poisoning/semantic_detector.py`, whose `SemanticInputRecord` structurally
excludes `original_label`/`poisoned`).

Two behaviors are worth stating explicitly rather than leaving implicit:

- A `BLOCK` content decision denies a high-impact tool call outright, with no
  review escalation, even when the target is on the pre-approved trust list. A
  legitimate high-impact action that P1 flags as a false-positive BLOCK has no
  recourse in this simulation.
- **Known containment gap**: a pre-approved trusted target combined with an
  `ALLOW` content decision always resolves to `ALLOW`. An attacker whose injected
  instruction both slips past the content detector *and* directs the action at a
  destination that is already trusted is not caught by this layer. This is the
  honest answer to the roadmap's research question — least privilege helps, but
  not always — and `confused_deputy_scenarios.py` deliberately includes a case that
  demonstrates it, so `evaluate_tool_policy.py` reports a non-zero
  `harmful_action_success_rate_with_policy` rather than a suspiciously perfect 0%.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

PERMISSIONS = ("READ_ONLY", "WRITE", "EXTERNAL_COMMUNICATION", "SENSITIVE_DATA")
HIGH_IMPACT_PERMISSIONS = frozenset({"WRITE", "EXTERNAL_COMMUNICATION", "SENSITIVE_DATA"})

DETECTOR_NAME = "s6-tool-call-policy"
DETECTOR_VERSION = "0.1.0"


@dataclass(frozen=True)
class ToolCall:
    """A structured request to invoke a tool, blind to why it was proposed."""

    tool_name: str
    target: str
    parameters: Mapping[str, str]


@dataclass(frozen=True)
class ToolRegistryEntry:
    permission: str
    trusted_targets: frozenset[str]


@dataclass(frozen=True)
class ToolPolicyResult:
    decision: str
    reasons: tuple[str, ...]


TOOL_REGISTRY: dict[str, ToolRegistryEntry] = {
    "read_email": ToolRegistryEntry(permission="READ_ONLY", trusted_targets=frozenset()),
    "search_documents": ToolRegistryEntry(permission="READ_ONLY", trusted_targets=frozenset()),
    "create_calendar_event": ToolRegistryEntry(
        permission="WRITE", trusted_targets=frozenset({"user-primary-calendar"})
    ),
    "delete_records": ToolRegistryEntry(permission="WRITE", trusted_targets=frozenset()),
    "send_email": ToolRegistryEntry(
        permission="EXTERNAL_COMMUNICATION",
        trusted_targets=frozenset({"user@company.example", "assistant-team@company.example"}),
    ),
    "access_secret": ToolRegistryEntry(permission="SENSITIVE_DATA", trusted_targets=frozenset()),
}

_TOOL_CALL_FIELD_NAMES = frozenset(field.name for field in fields(ToolCall))
assert _TOOL_CALL_FIELD_NAMES == frozenset({"tool_name", "target", "parameters"}), (
    "ToolCall must never carry ground-truth fields (e.g. actually_harmful) - "
    "evaluate_tool_call() must stay blind to why a call was proposed"
)
assert set(TOOL_REGISTRY) == {
    "read_email",
    "search_documents",
    "create_calendar_event",
    "delete_records",
    "send_email",
    "access_secret",
}
for _name, _entry in TOOL_REGISTRY.items():
    assert _entry.permission in PERMISSIONS, f"{_name} has an unknown permission: {_entry.permission}"
del _name, _entry


def evaluate_tool_call(tool_call: ToolCall, content_decision: str) -> ToolPolicyResult:
    """Decide ALLOW / HUMAN_REVIEW / DENY for a proposed tool call.

    Blind by construction: the only inputs are the structured `tool_call` and the
    content detector's own decision on whatever text nominally justified this
    call. No ground truth about attacker intent or actual harm is ever read here.
    """
    if content_decision not in ("ALLOW", "REVIEW", "BLOCK"):
        raise ValueError(f"unknown content_decision: {content_decision!r}")

    entry = TOOL_REGISTRY.get(tool_call.tool_name)
    if entry is None:
        return ToolPolicyResult("DENY", ("tool is not in the policy registry",))

    if entry.permission == "READ_ONLY":
        return ToolPolicyResult(
            "ALLOW", ("read-only actions are not gated by this policy layer",)
        )

    if content_decision == "BLOCK":
        return ToolPolicyResult(
            "DENY", ("high-impact action blocked: content detector flagged BLOCK",)
        )

    if tool_call.target not in entry.trusted_targets:
        return ToolPolicyResult(
            "HUMAN_REVIEW",
            ("high-impact action targets a destination outside the pre-approved trust list",),
        )

    if content_decision == "REVIEW":
        return ToolPolicyResult(
            "HUMAN_REVIEW",
            ("high-impact action to a trusted target, but content detector flagged REVIEW",),
        )

    return ToolPolicyResult(
        "ALLOW",
        ("high-impact action to a pre-approved trusted target with no content-detector signal",),
    )


def policy_metadata() -> dict[str, str]:
    """Return stable identity data for evaluation and audit records."""
    policy = {
        "name": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "permissions": list(PERMISSIONS),
        "high_impact_permissions": sorted(HIGH_IMPACT_PERMISSIONS),
        "registry": {
            name: {
                "permission": entry.permission,
                "trusted_targets": sorted(entry.trusted_targets),
            }
            for name, entry in sorted(TOOL_REGISTRY.items())
        },
    }
    canonical = json.dumps(policy, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return {
        "detector": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "config_hash": hashlib.sha256(canonical).hexdigest(),
    }


def append_audit_record(
    path: Path,
    tool_call: ToolCall,
    content_decision: str,
    result: ToolPolicyResult,
    *,
    extra: Mapping[str, object] | None = None,
) -> None:
    """Append one JSON line describing an allow/deny/human-review decision.

    This models a real production audit record. Callers must never pass
    ground-truth fields (e.g. `actually_harmful`, `triggered_by_untrusted_content`)
    via `extra` - a real audit trail cannot know, at decision time, whether an
    action was actually attacker-triggered or actually harmful. `extra` exists
    only for non-ground-truth context (e.g. a request id).
    """
    entry = TOOL_REGISTRY.get(tool_call.tool_name)
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool_name": tool_call.tool_name,
        "target": tool_call.target,
        "permission": entry.permission if entry is not None else None,
        "parameters": dict(tool_call.parameters),
        "content_decision": content_decision,
        "decision": result.decision,
        "reasons": list(result.reasons),
    }
    if extra:
        record.update(extra)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode="a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
