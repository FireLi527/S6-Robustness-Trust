from __future__ import annotations

import unittest

from confused_deputy_scenarios import SCENARIOS
from detector import detect_prompt_injection
from evaluate_approval_policy import simulate


CONTENT = {scenario.scenario_id: detect_prompt_injection(scenario.content).decision for scenario in SCENARIOS}


class ApprovalSimulationTests(unittest.TestCase):
    def test_informed_reviewer_never_approves_harm(self) -> None:
        rows = simulate("informed", "always", CONTENT)
        self.assertFalse(any(row["reviewer_granted"] and row["actually_harmful"] for row in rows))

    def test_rubber_stamp_admits_at_least_as_much_harm(self) -> None:
        def harm(rows):
            return sum(row["executed"] and row["actually_harmful"] for row in rows)

        self.assertGreaterEqual(harm(simulate("rubber_stamp", "always", CONTENT)), harm(simulate("informed", "always", CONTENT)))

    def test_hard_deny_tools_never_execute(self) -> None:
        rows = simulate("rubber_stamp", "always", CONTENT)
        for row in rows:
            if row["tool_name"] in ("access_secret", "delete_records"):
                self.assertFalse(row["executed"], row["scenario_id"])

    def test_persistent_approval_only_matches_exact_scope(self) -> None:
        rows = simulate("informed", "always", CONTENT)
        variants = [row for row in rows if row["phase"] == "parameter_variant"]
        self.assertFalse(any(row["matched_approval"] for row in variants))


if __name__ == "__main__":
    unittest.main()
