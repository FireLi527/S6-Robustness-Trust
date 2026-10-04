import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

import app
from approval_policy import ApprovalStore
from task_scope import TaskScopeStore
from tool_policy import ToolCall, evaluate_tool_call
from semantic_detector import SemanticAssessment


class TaskScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.approvals = ApprovalStore(Path(self.tmp.name) / "approvals.json")
        self.scopes = TaskScopeStore()
        self.question = "Review the release procedure without executing it."
        self.call = ToolCall("send_email", "outsider@example.org", {"body": "summary"})

    def apply(self, token, call=None, risk="ALLOW", question=None):
        call = call or self.call
        return self.scopes.apply(token, question or self.question, call, risk,
                                 evaluate_tool_call(call, risk), self.approvals)

    def confirm(self, mode="exact_action", call=None):
        return self.scopes.confirm(self.question, mode, call or self.call, True)

    def test_missing_scope_denies_even_trusted_target(self):
        call = ToolCall("send_email", "user@company.example", {})
        self.assertEqual(evaluate_tool_call(call, "ALLOW").decision, "ALLOW")
        self.assertEqual(self.apply("", call).decision, "DENY")

    def test_read_only_denies_writes_but_allows_read(self):
        token = self.confirm("read_only")
        self.assertEqual(self.apply(token).decision, "DENY")
        self.assertEqual(self.apply(token, ToolCall("read_email", "inbox", {})).decision, "ALLOW")

    def test_permanent_approval_cannot_escape_scope(self):
        self.approvals.grant(self.call, "always")
        self.assertEqual(self.apply(self.confirm("read_only")).decision, "DENY")
        self.assertEqual(self.apply(self.confirm()).matched, "always")

    def test_out_of_scope_does_not_consume_once(self):
        self.approvals.grant(self.call, "once")
        self.assertEqual(self.apply(self.confirm("read_only")).decision, "DENY")
        token = self.confirm()
        self.assertEqual(self.apply(token).matched, "once")
        self.assertEqual(self.apply(token).decision, "HUMAN_REVIEW")

    def test_exact_scope_binds_tool_target_parameters_and_task(self):
        token = self.confirm()
        for call in (ToolCall("read_email", self.call.target, self.call.parameters),
                     ToolCall("send_email", "other@example.org", self.call.parameters),
                     ToolCall("send_email", self.call.target, {"body": "changed"})):
            self.assertEqual(self.apply(token, call).decision, "DENY")
        self.assertEqual(self.apply(token, question="Publish the release").decision, "DENY")

    def test_blacklist_and_block_still_win(self):
        for name in ("access_secret", "delete_records"):
            call = ToolCall(name, "target", {})
            self.assertEqual(self.apply(self.confirm(call=call), call).decision, "DENY")
        self.approvals.grant(self.call, "always")
        self.assertEqual(self.apply(self.confirm(), risk="BLOCK").decision, "DENY")

    def test_expiry_eviction_and_explicit_confirmation(self):
        now = [0]
        self.scopes = TaskScopeStore(ttl=5, maximum=1, clock=lambda: now[0])
        token = self.confirm()
        now[0] = 5
        self.assertEqual(self.apply(token).reasons, ("scopeExpired",))
        self.confirm()
        self.assertEqual(self.apply(token).reasons, ("scopeRequired",))
        for question, confirmed in (("", True), (self.question, False), (self.question, "true")):
            with self.assertRaises(ValueError):
                self.scopes.confirm(question, "read_only", self.call, confirmed)

    def test_grant_rechecks_scope_and_risk(self):
        base = evaluate_tool_call(self.call, "ALLOW")
        for token, risk in ((self.confirm("read_only"), "ALLOW"), (self.confirm(), "REVIEW"), ("", "ALLOW")):
            with self.assertRaises(ValueError):
                self.scopes.grant(token, self.question, self.call, risk, base, self.approvals, "always")
        self.assertEqual(self.approvals.list(), [])


class ScopeHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in (("TASK_SCOPES", TaskScopeStore()),
                              ("APPROVAL_STORE", ApprovalStore(Path(self.tmp.name) / "approvals.json")),
                              ("TOOL_POLICY_AUDIT_LOG", Path(self.tmp.name) / "audit.jsonl")):
            p = patch.object(app, target, value)
            p.start(); self.addCleanup(p.stop)
        for target, value in (("extract_embeddings", {}),
                              ("assess_task_consistency", SemanticAssessment("ALLOW", 0., (), ()))):
            p = patch.object(app, target, return_value=value)
            p.start(); self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.S6RequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.payload = {"text": "Meeting at noon.", "question": "Summarize the meeting.",
                        "tool_name": "send_email", "target": "outside@example.org", "parameters": {}}

    def stop_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def post(self, endpoint, payload, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin: headers["Origin"] = origin
        request = Request(f"http://127.0.0.1:{self.server.server_port}/api/{endpoint}",
                          data=json.dumps(payload).encode(), headers=headers)
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_confirm_approve_detect_then_change_task(self):
        result = self.post("detect", self.payload)
        self.assertEqual(result["tool_policy"]["approval"]["final_decision"], "DENY")
        confirmed = self.post("task-scope", {**self.payload, "scope_mode":"exact_action", "confirmed":True})
        payload = {**self.payload, "task_scope_token":confirmed["task_scope_token"]}
        self.assertTrue(self.post("detect", payload)["tool_policy"]["approval"]["can_approve"])
        self.post("approvals", {**payload, "action":"grant", "mode":"always"})
        self.assertEqual(self.post("detect", payload)["tool_policy"]["approval"]["final_decision"], "ALLOW")
        payload["question"] = "Only review the document."
        self.assertEqual(self.post("detect", payload)["tool_policy"]["approval"]["final_decision"], "DENY")
        with self.assertRaises(HTTPError):
            self.post("approvals", {**payload, "action":"grant", "mode":"always"})

    def test_confirmation_cannot_be_implicit_or_cross_origin(self):
        for extra, origin in (({}, None), ({"confirmed":True}, "https://evil.example")):
            with self.assertRaises(HTTPError) as error:
                self.post("task-scope", {**self.payload, "scope_mode":"read_only", **extra}, origin)
            self.assertEqual(error.exception.code, 400)
