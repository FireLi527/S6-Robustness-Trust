from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from confused_deputy_scenarios import SCENARIOS
from detector import detect_prompt_injection
from tool_policy import (
    DETECTOR_NAME,
    DETECTOR_VERSION,
    HIGH_IMPACT_PERMISSIONS,
    PERMISSIONS,
    TOOL_REGISTRY,
    ToolCall,
    ToolPolicyResult,
    append_audit_record,
    evaluate_tool_call,
    policy_metadata,
)


class ToolRegistryTests(unittest.TestCase):
    def test_every_entry_has_a_valid_permission(self) -> None:
        for name, entry in TOOL_REGISTRY.items():
            self.assertIn(entry.permission, PERMISSIONS, name)

    def test_all_four_permission_tiers_are_present(self) -> None:
        observed = {entry.permission for entry in TOOL_REGISTRY.values()}
        self.assertEqual(observed, set(PERMISSIONS))

    def test_high_impact_tools_have_no_overlap_with_read_only(self) -> None:
        for entry in TOOL_REGISTRY.values():
            if entry.permission == "READ_ONLY":
                self.assertNotIn(entry.permission, HIGH_IMPACT_PERMISSIONS)
            else:
                self.assertIn(entry.permission, HIGH_IMPACT_PERMISSIONS)

    def test_delete_records_and_access_secret_have_no_trusted_targets(self) -> None:
        self.assertEqual(TOOL_REGISTRY["delete_records"].trusted_targets, frozenset())
        self.assertEqual(TOOL_REGISTRY["access_secret"].trusted_targets, frozenset())


class EvaluateToolCallTests(unittest.TestCase):
    def test_unknown_tool_is_denied(self) -> None:
        call = ToolCall(tool_name="not_a_real_tool", target="anywhere", parameters={})
        result = evaluate_tool_call(call, "ALLOW")
        self.assertEqual(result.decision, "DENY")

    def test_read_only_ignores_block_content_decision(self) -> None:
        call = ToolCall(tool_name="read_email", target="inbox", parameters={})
        result = evaluate_tool_call(call, "BLOCK")
        self.assertEqual(result.decision, "ALLOW")

    def test_high_impact_block_is_always_denied_even_for_trusted_target(self) -> None:
        call = ToolCall(
            tool_name="send_email", target="user@company.example", parameters={}
        )
        result = evaluate_tool_call(call, "BLOCK")
        self.assertEqual(result.decision, "DENY")

    def test_high_impact_trusted_target_allow_content_is_allowed(self) -> None:
        call = ToolCall(
            tool_name="send_email", target="user@company.example", parameters={}
        )
        result = evaluate_tool_call(call, "ALLOW")
        self.assertEqual(result.decision, "ALLOW")

    def test_high_impact_trusted_target_review_content_is_human_review(self) -> None:
        call = ToolCall(
            tool_name="send_email", target="user@company.example", parameters={}
        )
        result = evaluate_tool_call(call, "REVIEW")
        self.assertEqual(result.decision, "HUMAN_REVIEW")

    def test_high_impact_untrusted_target_allow_content_is_human_review(self) -> None:
        # The case that demonstrates least-privilege catching what content
        # detection missed: P1 says ALLOW, but the untrusted destination still
        # routes the action to a human.
        call = ToolCall(
            tool_name="send_email", target="attacker@evil.example", parameters={}
        )
        result = evaluate_tool_call(call, "ALLOW")
        self.assertEqual(result.decision, "HUMAN_REVIEW")

    def test_high_impact_untrusted_target_review_content_is_human_review(self) -> None:
        call = ToolCall(
            tool_name="send_email", target="attacker@evil.example", parameters={}
        )
        result = evaluate_tool_call(call, "REVIEW")
        self.assertEqual(result.decision, "HUMAN_REVIEW")

    def test_invalid_content_decision_raises(self) -> None:
        call = ToolCall(tool_name="send_email", target="user@company.example", parameters={})
        with self.assertRaises(ValueError):
            evaluate_tool_call(call, "UNKNOWN")

    def test_delete_records_never_reaches_allow(self) -> None:
        for content_decision in ("ALLOW", "REVIEW", "BLOCK"):
            call = ToolCall(tool_name="delete_records", target="anything", parameters={})
            result = evaluate_tool_call(call, content_decision)
            self.assertNotEqual(result.decision, "ALLOW", content_decision)

    def test_access_secret_never_reaches_allow(self) -> None:
        for content_decision in ("ALLOW", "REVIEW", "BLOCK"):
            call = ToolCall(tool_name="access_secret", target="anything", parameters={})
            result = evaluate_tool_call(call, content_decision)
            self.assertNotEqual(result.decision, "ALLOW", content_decision)


class PolicyMetadataTests(unittest.TestCase):
    def test_metadata_is_stable_and_complete(self) -> None:
        first = policy_metadata()
        second = policy_metadata()
        self.assertEqual(first, second)
        self.assertEqual(first["detector"], DETECTOR_NAME)
        self.assertEqual(first["version"], DETECTOR_VERSION)
        self.assertEqual(len(first["config_hash"]), 64)


class AppendAuditRecordTests(unittest.TestCase):
    def test_writes_one_parseable_json_line_with_documented_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            call = ToolCall(tool_name="send_email", target="user@company.example", parameters={"cc": "team"})
            result = ToolPolicyResult("ALLOW", ("some reason",))
            append_audit_record(path, call, "ALLOW", result)

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            for key in (
                "timestamp",
                "tool_name",
                "target",
                "permission",
                "parameters",
                "content_decision",
                "decision",
                "reasons",
            ):
                self.assertIn(key, record)
            self.assertEqual(record["tool_name"], "send_email")
            self.assertEqual(record["decision"], "ALLOW")

    def test_second_call_appends_rather_than_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            call = ToolCall(tool_name="read_email", target="inbox", parameters={})
            result = ToolPolicyResult("ALLOW", ("read-only",))
            append_audit_record(path, call, "ALLOW", result)
            append_audit_record(path, call, "ALLOW", result)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)

    def test_non_dict_mapping_parameters_round_trip(self) -> None:
        class FrozenMapping:
            def __init__(self, data: dict) -> None:
                self._data = data

            def keys(self):
                return self._data.keys()

            def __getitem__(self, key):
                return self._data[key]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            call = ToolCall(
                tool_name="read_email", target="inbox", parameters=FrozenMapping({"a": "b"})
            )
            result = ToolPolicyResult("ALLOW", ("read-only",))
            append_audit_record(path, call, "ALLOW", result)
            record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["parameters"], {"a": "b"})


class ScenarioBlindnessTests(unittest.TestCase):
    def test_tool_call_field_set_is_exactly_three_fields(self) -> None:
        field_names = frozenset(field.name for field in fields(ToolCall))
        self.assertEqual(field_names, frozenset({"tool_name", "target", "parameters"}))

    def test_evaluate_tool_call_signature_is_exactly_two_parameters(self) -> None:
        parameters = tuple(inspect.signature(evaluate_tool_call).parameters)
        self.assertEqual(parameters, ("tool_call", "content_decision"))


class ConfusedDeputyScenarioFixtureTests(unittest.TestCase):
    def test_scenario_ids_are_unique(self) -> None:
        ids = [scenario.scenario_id for scenario in SCENARIOS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_scenario_has_non_empty_content(self) -> None:
        for scenario in SCENARIOS:
            self.assertTrue(scenario.content.strip(), scenario.scenario_id)

    def test_every_scenario_tool_name_is_registered(self) -> None:
        for scenario in SCENARIOS:
            self.assertIn(scenario.tool_call.tool_name, TOOL_REGISTRY, scenario.scenario_id)

    def test_every_permission_tier_has_at_least_one_scenario(self) -> None:
        observed = {
            TOOL_REGISTRY[scenario.tool_call.tool_name].permission for scenario in SCENARIOS
        }
        self.assertEqual(observed, set(PERMISSIONS))

    def _run_live_pipeline(self) -> list[dict]:
        rows = []
        for scenario in SCENARIOS:
            content_result = detect_prompt_injection(scenario.content)
            policy_result = evaluate_tool_call(scenario.tool_call, content_result.decision)
            rows.append(
                {
                    "scenario": scenario,
                    "content_decision": content_result.decision,
                    "policy_decision": policy_result.decision,
                }
            )
        return rows

    def test_all_three_policy_decisions_are_represented(self) -> None:
        rows = self._run_live_pipeline()
        observed = {row["policy_decision"] for row in rows}
        self.assertEqual(observed, {"ALLOW", "HUMAN_REVIEW", "DENY"})

    def test_scenarios_commented_as_p1_allow_actually_get_allow(self) -> None:
        allow_scenario_ids = {
            "search_documents_benign",
            "calendar_benign_trusted_target",
            "calendar_benign_untrusted_target_friction",
            "calendar_attack_missed_by_p1_untrusted_target",
            "delete_records_benign_never_allow",
            "send_email_benign_trusted_target",
            "send_email_benign_untrusted_target_friction",
            "send_email_attack_missed_by_p1_untrusted_target",
            "send_email_attack_missed_by_p1_trusted_target_containment_gap",
            "access_secret_benign_never_allow",
            "access_secret_attack_missed_by_p1",
        }
        for row in self._run_live_pipeline():
            if row["scenario"].scenario_id in allow_scenario_ids:
                self.assertEqual(
                    row["content_decision"], "ALLOW", row["scenario"].scenario_id
                )

    def test_scenarios_commented_as_p1_block_actually_get_block(self) -> None:
        block_scenario_ids = {
            "read_only_attack_content_is_exempt",
            "calendar_attack_blocked",
            "delete_records_attack_blocked",
            "send_email_attack_blocked",
            "access_secret_attack_blocked",
        }
        for row in self._run_live_pipeline():
            if row["scenario"].scenario_id in block_scenario_ids:
                self.assertEqual(
                    row["content_decision"], "BLOCK", row["scenario"].scenario_id
                )

    def test_scenarios_commented_as_p1_review_actually_get_review(self) -> None:
        review_scenario_ids = {
            "delete_records_attack_review_content",
            "send_email_benign_review_content_trusted_target",
        }
        for row in self._run_live_pipeline():
            if row["scenario"].scenario_id in review_scenario_ids:
                self.assertEqual(
                    row["content_decision"], "REVIEW", row["scenario"].scenario_id
                )

    def test_at_least_three_scenarios_demonstrate_core_containment_case(self) -> None:
        # P1 misses the attack (ALLOW) but P3 still routes it to a human because
        # the target is untrusted -- the direct demonstration of the roadmap's
        # research question.
        rows = self._run_live_pipeline()
        core_cases = [
            row
            for row in rows
            if row["scenario"].triggered_by_untrusted_content
            and row["content_decision"] == "ALLOW"
            and row["policy_decision"] == "HUMAN_REVIEW"
        ]
        self.assertGreaterEqual(len(core_cases), 3)

    def test_at_least_one_scenario_demonstrates_the_known_containment_gap(self) -> None:
        rows = self._run_live_pipeline()
        gap_cases = [
            row
            for row in rows
            if row["scenario"].actually_harmful
            and row["content_decision"] == "ALLOW"
            and row["policy_decision"] == "ALLOW"
        ]
        self.assertGreaterEqual(len(gap_cases), 1)


class AuditLogNeverLeaksGroundTruthTests(unittest.TestCase):
    def test_audit_log_contains_no_ground_truth_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            for scenario in SCENARIOS:
                content_result = detect_prompt_injection(scenario.content)
                policy_result = evaluate_tool_call(
                    scenario.tool_call, content_result.decision
                )
                append_audit_record(
                    path, scenario.tool_call, content_result.decision, policy_result
                )

            for line in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                self.assertNotIn("actually_harmful", record)
                self.assertNotIn("triggered_by_untrusted_content", record)


if __name__ == "__main__":
    unittest.main()
