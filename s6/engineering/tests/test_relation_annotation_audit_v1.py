"""Representation-audit contracts: literal diffs only, never a score override."""
import copy
import json
from pathlib import Path
import unittest
from s6.prompt_injection.relation_annotation_audit_v1 import (attribute_side, covered, parse, reference_inventory,
                                                             summarize_attribution)


def act(operation, bindings, conditions=(), kind="execute"):
    return {"operation": operation, "kind": kind, "conditions": list(conditions), "evidence": "x",
            "bindings": [{"role": r, "text": t, "status": "unspecified" if t is None else s} for r, t, s in bindings]}


GOLD = {"actions": [act("删除", [("source", "scratch/logs", "explicit"), ("object", "日志", "explicit")], ["早于2020"])],
        "constraints": ["保留其他文件"], "missing_context": []}


class AnnotationAuditTests(unittest.TestCase):
    def categories(self, prediction):
        result = attribute_side(prediction, GOLD)
        return [u["category"] for u in result["actions"] + result["lists"]], result

    def test_exact_reference_is_exact(self):
        self.assertEqual(self.categories(copy.deepcopy(GOLD))[0], ["exact", "exact"])

    def test_role_swap_is_representation_only(self):
        pred = copy.deepcopy(GOLD); pred["actions"][0]["bindings"][0]["role"] = "environment"
        cats, result = self.categories(pred)
        self.assertEqual(cats[0], "representation_only")
        self.assertIn("role", result["actions"][0]["diffs"])

    def test_condition_in_parameter_is_moved_not_missing(self):
        pred = copy.deepcopy(GOLD); pred["actions"][0]["conditions"] = []
        pred["actions"][0]["bindings"].append({"role": "parameter", "text": "早于2020", "status": "explicit"})
        cats, result = self.categories(pred)
        self.assertEqual(cats[0], "representation_only")
        self.assertIn("condition_moved", result["actions"][0]["diffs"])

    def test_absent_information_is_missing(self):
        pred = copy.deepcopy(GOLD); pred["actions"][0]["conditions"] = []; pred["constraints"] = []
        cats, _ = self.categories(pred)
        self.assertEqual(cats, ["information_missing", "information_missing"])

    def test_constraint_as_action_is_representation(self):
        pred = copy.deepcopy(GOLD); pred["constraints"] = []
        pred["actions"].append(act("保留", [("object", "其他文件", "explicit")]))
        cats, result = self.categories(pred)
        self.assertEqual(cats[1], "representation_only")
        self.assertTrue(result["extra_actions"][0]["grounded_in_reference"])

    def test_reordered_actions_flagged(self):
        gold = copy.deepcopy(GOLD); gold["actions"].append(act("报告", [("object", None, "")]))
        pred = copy.deepcopy(gold); pred["actions"].reverse()
        self.assertIn("action_order", attribute_side(pred, gold)["actions"][0]["diffs"])

    def test_invalid_output_not_parsed_and_counted(self):
        self.assertIsNone(parse({"score": {"valid": False}, "text": "{}"}))
        summary = summarize_attribution([{"attribution": attribute_side(None, GOLD), "reference_units": 2}])
        self.assertEqual(summary["unit_categories"], {"contract_invalid": 2})

    def test_evidence_excluded_from_coverage(self):
        pred = copy.deepcopy(GOLD); pred["constraints"] = []
        pred["actions"][0]["evidence"] = "保留其他文件"
        self.assertEqual(self.categories(pred)[0][1], "information_missing")
        self.assertFalse(covered("日志", ["x"]))

    def test_inventory_on_frozen_references(self):
        path = Path(__file__).resolve().parents[3] / "data/bipia/relation_scale_training_v1/samples.json"
        rows = [r for r in json.loads(path.read_text(encoding="utf-8")) if r["variant"] == "core"]
        sides = [{"id": r["id"], "side": "content", "split": r["split"], "target": r["targets"]["content"]} for r in rows]
        result = reference_inventory(sides)
        self.assertEqual(result["reference_sides"], 102)
        self.assertEqual(len(result["unknown_status_rows"]), sum(bool(r["targets"]["content"]["missing_context"]) for r in rows))


if __name__ == "__main__":
    unittest.main()
