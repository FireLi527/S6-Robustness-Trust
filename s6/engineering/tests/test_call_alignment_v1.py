"""Call-level task alignment rules and metric denominators."""
import json
from pathlib import Path
import unittest
from s6.prompt_injection.call_alignment_v1 import align, profile
from s6.prompt_injection.evaluate_call_alignment_v1 import decide, metrics

ROOT = Path(__file__).resolve().parents[3]


class CallAlignmentTests(unittest.TestCase):
    def test_profile_splits_service_and_verb(self):
        self.assertEqual((profile("GmailSendEmail")["service"], profile("GmailSendEmail")["action"]), ("gmail", "WRITE"))
        self.assertEqual(profile("EpicFHIRGetPatientDetails")["service"], "epicfhir")
        self.assertEqual(profile("FooBarBaz")["action"], "UNKNOWN")

    def test_decisions(self):
        task = "Find the most recent email from news@example.com."
        self.assertEqual(align(task, "GmailSearchEmails")["final"], "ALLOW")
        self.assertEqual(align(task, "GmailSendEmail")["final"], "DENY")
        self.assertEqual(align(task, "AmazonViewSavedAddresses")["final"], "REVIEW")
        self.assertEqual(align(task, "BankManagerPayBill")["final"], "DENY")
        self.assertEqual(align(task, "FooBarBaz")["final"], "REVIEW")
        self.assertEqual(align("Please send an email to my boss.", "GmailSendEmail")["final"], "REVIEW")

    def test_alignment_never_looser_than_p3(self):
        result = align("Please send an email to my boss.", "GmailSendEmail")
        self.assertEqual((result["alignment"], result["p3"], result["final"]), ("ALLOW", "REVIEW", "REVIEW"))
        self.assertEqual(result["tool_authorization"], "not_granted")

    def test_decisions_do_not_read_provenance(self):
        row = {"id": "x", "task": "Read my tweet.", "tool_name": "TwitterManagerReadTweet", "provenance": "user"}
        flipped = {**row, "provenance": "injected", "kind": "dh", "case": "c", "step": 0, "user_tool": "TwitterManagerReadTweet"}
        self.assertEqual(decide([row])[0]["decisions"], decide([flipped])[0]["decisions"])

    def test_chain_needs_every_step(self):
        items = [{"provenance": "injected", "kind": "ds", "case": "c1", "step": 0, "same_service": False,
                  "decisions": {"s": "ALLOW"}},
                 {"provenance": "injected", "kind": "ds", "case": "c1", "step": 1, "same_service": False,
                  "decisions": {"s": "DENY"}},
                 {"provenance": "user", "decisions": {"s": "ALLOW"}}]
        result = metrics(items, "s")
        self.assertEqual(result["attack_chains_fully_auto_allowed"]["hits"], 0)
        self.assertEqual(result["ds_first_step_read_auto_allowed"]["hits"], 1)
        self.assertEqual(result["benign_auto_allowed"], {"hits": 1, "n": 1, "rate": 1.0})

    def test_frozen_split_disjoint(self):
        dev = json.loads((ROOT / "data/bipia/call_alignment_v1/development.json").read_text(encoding="utf-8"))
        test = json.loads((ROOT / "data/bipia/call_alignment_v1/test.json").read_text(encoding="utf-8"))
        self.assertFalse({r["task"] for r in dev["benign"]} & {r["task"] for r in test["benign"]})
        self.assertFalse({r["attacker_instruction"] for r in dev["attack"]} & {r["attacker_instruction"] for r in test["attack"]})


if __name__ == "__main__":
    unittest.main()
