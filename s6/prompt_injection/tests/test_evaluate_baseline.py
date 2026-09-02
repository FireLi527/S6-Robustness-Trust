from __future__ import annotations

import unittest

import pandas as pd

from evaluate_baseline import attack_category, failure_rows, summarize_split


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            [
                {
                    "split": "test",
                    "sample_id": 0,
                    "content_sha256": "a",
                    "ground_truth": "ATTACK",
                    "decision": "BLOCK",
                    "score": 6,
                    "latency_ms": 1.0,
                    "reasons": "signal",
                    "task_name": "email",
                    "attack_name": "Category-0",
                    "attack_category": "Category",
                    "position": "start",
                    "question": "q",
                },
                {
                    "split": "test",
                    "sample_id": 1,
                    "content_sha256": "b",
                    "ground_truth": "ATTACK",
                    "decision": "ALLOW",
                    "score": 0,
                    "latency_ms": 2.0,
                    "reasons": "",
                    "task_name": "email",
                    "attack_name": "Category-0",
                    "attack_category": "Category",
                    "position": "end",
                    "question": "q",
                },
                {
                    "split": "test",
                    "sample_id": 2,
                    "content_sha256": "c",
                    "ground_truth": "CLEAN",
                    "decision": "REVIEW",
                    "score": 2,
                    "latency_ms": 3.0,
                    "reasons": "signal",
                    "task_name": "email",
                    "attack_name": "",
                    "attack_category": "",
                    "position": "",
                    "question": "q",
                },
                {
                    "split": "test",
                    "sample_id": 3,
                    "content_sha256": "d",
                    "ground_truth": "CLEAN",
                    "decision": "ALLOW",
                    "score": 0,
                    "latency_ms": 4.0,
                    "reasons": "",
                    "task_name": "email",
                    "attack_name": "",
                    "attack_category": "",
                    "position": "",
                    "question": "q",
                },
            ]
        )

    def test_category_parsing_preserves_hyphens(self) -> None:
        self.assertEqual(attack_category("Multi-part Category-4"), "Multi-part Category")

    def test_summary_metrics(self) -> None:
        summary = summarize_split(self.frame)
        self.assertEqual(summary["attack_detection_rate"], 0.5)
        self.assertEqual(summary["false_positive_rate"], 0.5)
        self.assertEqual(summary["precision"], 0.5)
        self.assertEqual(summary["f1"], 0.5)
        self.assertEqual(summary["latency"]["all"]["median_ms"], 2.5)

    def test_failures_include_miss_and_false_positive(self) -> None:
        failures = failure_rows(self.frame)
        self.assertEqual(len(failures), 2)
        self.assertEqual(
            set(failures["failure_type"]),
            {"MISSED_ATTACK", "CLEAN_FALSE_POSITIVE"},
        )


if __name__ == "__main__":
    unittest.main()
