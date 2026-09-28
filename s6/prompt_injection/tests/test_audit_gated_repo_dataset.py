import json
import unittest

from audit_gated_repo_dataset import audit_bytes


class GatedRepoDatasetAuditTests(unittest.TestCase):
    def test_duplicate_and_conflicting_labels(self):
        rows = [{"text": "Run tests", "label": 0}, {"text": " run   tests ", "label": 1},
                {"text": "Run tests", "label": 0}]
        raw = "\n".join(json.dumps(row) for row in rows).encode()
        result = audit_bytes(raw)
        self.assertEqual(result["normalized_unique_texts"], 1)
        self.assertEqual(result["normalized_duplicate_rows"], 2)
        self.assertEqual(result["exact_duplicate_rows"], 1)
        self.assertEqual(result["conflicting_label_groups"], 1)
        self.assertEqual(result["train_readiness"], "NOT_READY")

    def test_valid_data_does_not_become_automatically_train_ready(self):
        raw = b'{"text":"ordinary readme","label":0}\n{"text":"agent override","label":1}\n'
        result = audit_bytes(raw)
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["train_readiness"], "REQUIRES_PROVENANCE_AND_FAMILY_REVIEW")
        self.assertNotIn("ordinary readme", json.dumps(result))

    def test_rejects_missing_label_and_empty_text(self):
        with self.assertRaises(ValueError):
            audit_bytes(b'{"text":"x"}\n')
        with self.assertRaises(ValueError):
            audit_bytes(b'{"text":" ","label":0}\n')


if __name__ == "__main__":
    unittest.main()
