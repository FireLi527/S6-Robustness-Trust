"""Replay frozen Code comment-signal metrics and provenance checks."""

import csv
import hashlib
import json
import unittest

from code_context_signal import assess_comment_redirection
from evaluate_code_context_v1 import DATA, RESULTS, SIGNAL, samples, summarize


class CodeContextExperimentTests(unittest.TestCase):
    def test_confirmation_protocol_and_signal_hash(self):
        protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
        selection = json.loads((RESULTS / "selection.json").read_text(encoding="utf-8"))
        self.assertEqual(selection["signal_sha256"], hashlib.sha256(SIGNAL.read_bytes()).hexdigest())
        self.assertEqual(selection["confirmation_data_sha256"], protocol["samples_sha256"])
        sources = protocol["source_manifest"]
        self.assertEqual(len(sources), 100)
        self.assertEqual(len({source["source_id"] for source in sources}), 100)
        self.assertTrue(all(source["source_id"].startswith("sklearn/") for source in sources))
        if (DATA / "samples.jsonl").exists():
            _, rows = samples()
            self.assertEqual(len(rows), 300)

    def test_confirmation_metrics_replay(self):
        summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
        with (RESULTS / "predictions.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 300)
        for row in rows:
            row["label"] = int(row["label"])
            for key in ("rule", "supervised", "comment", "rule_or_comment"):
                row[key] = row[key] == "True"
        self.assertEqual(summarize(rows), summary["confirmation_metrics"])
        self.assertFalse(assess_comment_redirection("# Normal function comment.")["affects_tool_policy"])


if __name__ == "__main__":
    unittest.main()
