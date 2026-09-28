"""Integrity checks for the source-separated Code evaluation."""

import csv
import json
import unittest

from evaluate_code_independent_v2 import DATA, RESULTS, digest, rates


class IndependentCodeEvaluationTests(unittest.TestCase):
    def test_frozen_sources_and_templates(self):
        if not (DATA / "samples.jsonl").exists():
            self.skipTest("Local standard-library snippets not generated")
        protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
        raw = (DATA / "samples.jsonl").read_bytes()
        self.assertEqual(digest(raw), protocol["samples_sha256"])
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        self.assertEqual(len(rows), 600)
        for split in ("development", "test"):
            subset = [row for row in rows if row["split"] == split]
            self.assertEqual(len(subset), 300)
            self.assertEqual(sum(row["label"] == 0 for row in subset), 100)
            self.assertEqual(len({row["source_id"] for row in subset}), 100)
        development = {row["source_id"] for row in rows if row["split"] == "development"}
        test = {row["source_id"] for row in rows if row["split"] == "test"}
        self.assertFalse(development & test)
        self.assertFalse(any("site-packages" in row["source_id"] or "dist-packages" in row["source_id"]
                             for row in rows))
        self.assertFalse(set(protocol["templates"]["development"]) & set(protocol["templates"]["test"]))

    def test_report_metrics_replay(self):
        summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
        with (RESULTS / "predictions.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 600)
        for row in rows:
            row["label"] = int(row["label"])
            for key in ("rule", "supervised", "union"):
                row[key] = row[key] == "True"
        for split in ("development", "test"):
            subset = [row for row in rows if row["split"] == split]
            for detector in ("rule", "supervised", "union"):
                self.assertEqual(rates(subset, detector), summary["splits"][split][detector])


if __name__ == "__main__":
    unittest.main()
