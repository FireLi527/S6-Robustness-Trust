"""P3.1 explicit user approvals layered on top of the frozen P3 policy.

Deliberately stricter than P3 in one place: a content `BLOCK` denies every tool call,
including read-only ones that P3 exempts, so blocked content cannot drive any action.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from tool_policy import TOOL_REGISTRY, ToolCall, ToolPolicyResult

HARD_DENY_TOOLS = frozenset({"access_secret", "delete_records"})


def _scope_payload(call: ToolCall) -> dict[str, object]:
    return {
        "tool_name": call.tool_name,
        "target": call.target,
        "parameters": dict(sorted(call.parameters.items())),
    }


def scope_id(call: ToolCall) -> str:
    canonical = json.dumps(_scope_payload(call), ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class ApprovalResult:
    decision: str
    reasons: tuple[str, ...]
    scope_id: str
    matched: str | None = None
    can_approve: bool = False


class ApprovalStore:
    """Exact-scope approvals; one-time entries remain in memory, permanent ones use JSON."""

    def __init__(self, path: Path):
        self.path = path
        self._once: set[str] = set()
        self._lock = threading.RLock()

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = raw.get("approvals", {}) if isinstance(raw, dict) else {}
        return entries if isinstance(entries, dict) else {}

    def _save(self, entries: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "approvals": entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def grant(self, call: ToolCall, mode: str) -> str:
        if mode not in {"once", "always"}:
            raise ValueError("mode must be 'once' or 'always'")
        entry = TOOL_REGISTRY.get(call.tool_name)
        if entry is None:
            raise ValueError("unknown tools cannot be approved")
        if call.tool_name in HARD_DENY_TOOLS:
            raise ValueError("this tool is on the hard-deny list")
        if entry.permission == "READ_ONLY":
            raise ValueError("read-only tools do not require approval")
        key = scope_id(call)
        with self._lock:
            if mode == "once":
                self._once.add(key)
            else:
                entries = self._load()
                entries[key] = _scope_payload(call)
                self._save(entries)
        return key

    def revoke(self, key: str) -> bool:
        with self._lock:
            removed = key in self._once
            self._once.discard(key)
            entries = self._load()
            if key in entries:
                del entries[key]
                self._save(entries)
                removed = True
            return removed

    def list(self) -> list[dict[str, object]]:
        with self._lock:
            entries = self._load()
            return [{"scope_id": key, "mode": "always", **value} for key, value in sorted(entries.items())]

    def apply(self, call: ToolCall, content_decision: str, base: ToolPolicyResult) -> ApprovalResult:
        key = scope_id(call)
        if call.tool_name in HARD_DENY_TOOLS:
            return ApprovalResult("DENY", ("tool is on the P3.1 hard-deny list",), key)
        if content_decision == "BLOCK" or base.decision == "DENY":
            return ApprovalResult("DENY", base.reasons, key)
        if base.decision == "ALLOW":
            return ApprovalResult("ALLOW", base.reasons, key)
        if content_decision != "ALLOW":
            return ApprovalResult("HUMAN_REVIEW", base.reasons, key, can_approve=False)
        with self._lock:
            if key in self._once:
                self._once.remove(key)
                return ApprovalResult("ALLOW", ("matched one-time user approval",), key, "once")
            if key in self._load():
                return ApprovalResult("ALLOW", ("matched persistent user approval",), key, "always")
        return ApprovalResult("HUMAN_REVIEW", base.reasons, key, can_approve=True)
