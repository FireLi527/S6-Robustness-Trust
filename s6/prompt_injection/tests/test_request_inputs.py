import unittest

from request_inputs import content_text, tool_call


class RequestInputTests(unittest.TestCase):
    def test_content_preserves_task_binding_whitespace(self):
        self.assertEqual(content_text({"text": "  body\n"}), "  body\n")

    def test_missing_empty_or_non_string_content_is_rejected(self):
        for payload in ({}, {"text": None}, {"text": "  "}, {"text": 42}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                content_text(payload)

    def test_normalization_preserves_exact_parameters(self):
        payload = {"tool_name": " send_email ", "target": " user@example.org ",
                   "parameters": {"body": " keep spaces "}}
        call = tool_call(payload, required=True)
        self.assertEqual(call.tool_name, "send_email")
        self.assertEqual(call.target, "user@example.org")
        self.assertEqual(call.parameters, {"body": " keep spaces "})
        payload["parameters"]["body"] = "changed"
        self.assertEqual(call.parameters["body"], " keep spaces ")

    def test_detection_allows_absent_tool_but_approval_does_not(self):
        self.assertEqual(tool_call({}).tool_name, "")
        with self.assertRaises(ValueError):
            tool_call({}, required=True)

    def test_both_call_sites_reject_bad_shapes(self):
        for payload in ({"tool_name": None}, {"target": []}, {"parameters": []},
                        {"parameters": {"body": 1}}, {"parameters": {1: "body"}}):
            for required in (False, True):
                with self.subTest(payload=payload, required=required), self.assertRaises(ValueError):
                    tool_call({"tool_name": "send_email", **payload}, required=required)
