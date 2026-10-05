"""ASB trusted manifest: registration-time scoping, decision function blind to provenance."""
import inspect
import unittest
from s6.prompt_injection.asb_trusted_manifest_v1 import decide, manifest


class ManifestBuildTests(unittest.TestCase):
    def test_manifest_only_includes_normal_tools(self):
        agents = [{"agent": "a", "tools": [
            {"name": "normal_tool", "provenance": "normal"},
            {"name": "AttackTool", "provenance": "attack"},
        ]}]
        self.assertEqual(manifest(agents), {"a": frozenset({"normal_tool"})})

    def test_manifest_is_per_agent(self):
        agents = [
            {"agent": "a", "tools": [{"name": "x", "provenance": "normal"}]},
            {"agent": "b", "tools": [{"name": "y", "provenance": "normal"}]},
        ]
        result = manifest(agents)
        self.assertEqual(result["a"], frozenset({"x"}))
        self.assertEqual(result["b"], frozenset({"y"}))


class DecisionBlindnessTests(unittest.TestCase):
    def test_decide_signature_has_no_provenance_or_ground_truth_field(self):
        params = list(inspect.signature(decide).parameters)
        self.assertEqual(params, ["tool_name", "trusted"])

    def test_decide_allows_only_manifest_members(self):
        trusted = frozenset({"medical_database", "prescription_manager"})
        self.assertTrue(decide("medical_database", trusted))
        self.assertFalse(decide("PatientDataTheft", trusted))

    def test_decide_is_exact_name_match_not_substring(self):
        trusted = frozenset({"medical_database"})
        self.assertFalse(decide("medical_database_extended", trusted))


if __name__ == "__main__":
    unittest.main()
