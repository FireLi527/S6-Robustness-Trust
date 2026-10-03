"""Cross-source frozen baseline summary contract (no model)."""
import unittest
from s6.prompt_injection.evaluate_baseline_cross_source_v1 import summarize


class CrossSourceSummaryTests(unittest.TestCase):
    def test_review_counts_as_detection_and_p2_not_applicable_without_task(self):
        items = [{"id": "injecagent-dh-1", "source": "injecagent", "subset": "injecagent-dh", "label": 1,
                  "rule": "REVIEW", "semantic": "ALLOW", "hybrid": "REVIEW"},
                 {"id": "injecagent-dh-2", "source": "injecagent", "subset": "injecagent-dh", "label": 1,
                  "rule": "ALLOW", "semantic": "BLOCK", "hybrid": "BLOCK"},
                 {"id": "notinject-one-1", "source": "notinject", "subset": "notinject-one", "label": 0,
                  "rule": "BLOCK", "semantic": None, "hybrid": "BLOCK"}]
        result = summarize(items)
        self.assertEqual(result["injecagent"]["rule"]["detection_rate"]["hits"], 1)
        self.assertEqual(result["injecagent"]["hybrid"]["detection_rate"]["hits"], 2)
        self.assertEqual(result["injecagent"]["semantic"]["block"]["hits"], 1)
        self.assertEqual(result["notinject"]["semantic"], "not_applicable_no_user_task")
        self.assertEqual(result["notinject"]["rule"]["false_alarm_rate"], {"hits": 1, "n": 1, "rate": 1.0})


if __name__ == "__main__":
    unittest.main()
