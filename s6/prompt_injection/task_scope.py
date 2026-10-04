"""Live-only user-confirmed task scope; does not change frozen P3/P3.1 benchmarks.

Tokens are issued only by the confirmation API, not from model output or content.
This is an authorization simulation, not a tool executor or user authentication.
"""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import secrets
import threading
import time

from approval_policy import ApprovalResult, scope_id
from tool_policy import TOOL_REGISTRY


@dataclass(frozen=True)
class Scope:
    question_hash: str
    mode: str
    action_hash: str
    expires: float


class TaskScopeStore:
    def __init__(self, ttl=3600, maximum=1024, clock=time.monotonic):
        self.ttl, self.maximum, self.clock = ttl, maximum, clock
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def confirm(self, question, mode, call, confirmed):
        if confirmed is not True or not isinstance(question, str) or not question.strip():
            raise ValueError("scopeNeedsTask")
        if mode not in {"read_only", "exact_action"}:
            raise ValueError("scopeInvalidMode")
        if mode == "exact_action" and call.tool_name not in TOOL_REGISTRY:
            raise ValueError("scopeUnknownTool")
        token = secrets.token_urlsafe(32)
        scope = Scope(self._question_hash(question), mode,
                      scope_id(call) if mode == "exact_action" else "", self.clock() + self.ttl)
        with self._lock:
            self._items[token] = scope
            while len(self._items) > self.maximum:
                self._items.popitem(last=False)
        return token

    @staticmethod
    def _question_hash(question):
        return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()

    def check(self, token, question, call):
        if not isinstance(token, str):
            return "scopeRequired"
        with self._lock:
            scope = self._items.get(token)
        if scope is None:
            return "scopeRequired"
        if self.clock() >= scope.expires:
            return "scopeExpired"
        if scope.question_hash != self._question_hash(question):
            return "scopeTaskChanged"
        entry = TOOL_REGISTRY.get(call.tool_name)
        if entry is None:
            return "scopeUnknownTool"
        if scope.mode == "read_only":
            return None if entry.permission == "READ_ONLY" else "scopeReadOnlyDenied"
        return None if scope.action_hash == scope_id(call) else "scopeActionChanged"

    def apply(self, token, question, call, content_decision, base, approvals):
        reason = self.check(token, question, call)
        if reason:
            return ApprovalResult("DENY", (reason,), scope_id(call))
        return approvals.apply(call, content_decision, base)

    def grant(self, token, question, call, content_decision, base, approvals, mode):
        reason = self.check(token, question, call)
        if reason:
            raise ValueError(reason)
        # Recheck current content at grant time; never consume a one-time approval here.
        if content_decision != "ALLOW" or base.decision != "HUMAN_REVIEW":
            raise ValueError("scopeNotApprovable")
        return approvals.grant(call, mode)
