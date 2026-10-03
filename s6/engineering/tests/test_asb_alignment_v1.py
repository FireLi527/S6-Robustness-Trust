"""ASB semantic alignment: rule families and pre-declared selection."""
import unittest
from s6.prompt_injection.asb_alignment_v1 import allowed, select, tool_text


class AsbAlignmentTests(unittest.TestCase):
    def test_rule_families(self):
        self.assertEqual(allowed([0.5, 0.2, 0.4], ("threshold", 0.4)), [True, False, True])
        self.assertEqual(allowed([0.5, 0.2, 0.4], ("top_k", 1)), [True, False, False])

    def test_selection_respects_attack_cap(self):
        grid = {("threshold", 0.1): {"benign_allow": 1.0, "attack_allow": 0.5},
                ("threshold", 0.5): {"benign_allow": 0.6, "attack_allow": 0.04},
                ("top_k", 1): {"benign_allow": 0.5, "attack_allow": 0.01}}
        self.assertEqual(select(grid), ("threshold", 0.5))
        self.assertEqual(select({("top_k", 2): {"benign_allow": 0.9, "attack_allow": 0.2},
                                 ("top_k", 1): {"benign_allow": 0.5, "attack_allow": 0.1}}), ("top_k", 1))

    def test_tool_text_splits_names(self):
        self.assertTrue(tool_text({"name": "ResourceAllocationHijack", "description": "d"}).startswith("Resource Allocation Hijack"))


if __name__ == "__main__":
    unittest.main()
