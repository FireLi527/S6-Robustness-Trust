from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from approval_policy import ApprovalStore, scope_id
from tool_policy import ToolCall, evaluate_tool_call


class ApprovalPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "approvals.json"
        self.store = ApprovalStore(self.path)
        self.call = ToolCall("send_email", "new@example.com", {"subject": "status"})

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def apply(self, call: ToolCall, content: str = "ALLOW"):
        return self.store.apply(call, content, evaluate_tool_call(call, content))

    def test_unapproved_high_impact_scope_requires_review(self) -> None:
        result = self.apply(self.call)
        self.assertEqual(result.decision, "HUMAN_REVIEW")
        self.assertTrue(result.can_approve)

    def test_one_time_approval_is_exact_and_consumed(self) -> None:
        self.store.grant(self.call, "once")
        mismatch = ToolCall("send_email", "other@example.com", {"subject": "status"})
        self.assertEqual(self.apply(mismatch).decision, "HUMAN_REVIEW")
        self.assertEqual(self.apply(self.call).matched, "once")
        self.assertEqual(self.apply(self.call).decision, "HUMAN_REVIEW")

    def test_persistent_approval_survives_new_store_and_can_be_revoked(self) -> None:
        key = self.store.grant(self.call, "always")
        reopened = ApprovalStore(self.path)
        result = reopened.apply(self.call, "ALLOW", evaluate_tool_call(self.call, "ALLOW"))
        self.assertEqual(result.matched, "always")
        self.assertEqual(reopened.list()[0]["scope_id"], scope_id(self.call))
        self.assertTrue(reopened.revoke(key))
        self.assertEqual(reopened.list(), [])

    def test_parameter_change_does_not_match(self) -> None:
        self.store.grant(self.call, "always")
        changed = ToolCall("send_email", "new@example.com", {"subject": "different"})
        self.assertEqual(self.apply(changed).decision, "HUMAN_REVIEW")

    def test_hard_deny_tools_cannot_be_approved(self) -> None:
        call = ToolCall("access_secret", "vault", {})
        with self.assertRaises(ValueError):
            self.store.grant(call, "always")
        result = self.store.apply(call, "ALLOW", evaluate_tool_call(call, "ALLOW"))
        self.assertEqual(result.decision, "DENY")

    def test_block_or_review_signal_is_never_overridden(self) -> None:
        self.store.grant(self.call, "always")
        blocked = self.store.apply(self.call, "BLOCK", evaluate_tool_call(self.call, "BLOCK"))
        reviewed = self.store.apply(self.call, "REVIEW", evaluate_tool_call(self.call, "REVIEW"))
        self.assertEqual(blocked.decision, "DENY")
        self.assertEqual(reviewed.decision, "HUMAN_REVIEW")
        self.assertIsNone(reviewed.matched)

    def test_unknown_and_read_only_tools_are_not_approvable(self) -> None:
        for call in (ToolCall("unknown", "x", {}), ToolCall("read_email", "inbox", {})):
            with self.assertRaises(ValueError):
                self.store.grant(call, "once")


if __name__ == "__main__":
    unittest.main()
