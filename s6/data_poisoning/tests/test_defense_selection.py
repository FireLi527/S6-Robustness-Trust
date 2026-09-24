import unittest
from prepare_stl10_defense import select_rows

class DefenseSelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(sample_id=str(i), source_relpath=f"{i}.png", sha256=str(i), assigned_label=str(i%2)) for i in range(20)]
        self.predictions = {str(i): {"decision": "ALLOW" if i >= 4 else ("REVIEW" if i < 2 else "QUARANTINE")} for i in range(20)}

    def test_withholds_both_review_and_quarantine_without_relabeling(self):
        selected = select_rows(self.rows, self.predictions, 3)
        self.assertEqual(selected["semantic"][1], ["0", "1", "2", "3"])
        self.assertEqual(selected["semantic"][0], self.rows[4:])
        self.assertEqual(len(selected["random"][0]), 16)
        self.assertEqual(selected, select_rows(self.rows, self.predictions, 3))

    def test_rejects_missing_or_unknown_decisions(self):
        bad = dict(self.predictions); bad.pop("0")
        with self.assertRaises(ValueError): select_rows(self.rows, bad, 3)
        bad = dict(self.predictions); bad["0"] = {"decision": "UNKNOWN"}
        with self.assertRaises(ValueError): select_rows(self.rows, bad, 3)

    def test_clean_all_allow_retains_every_row(self):
        predictions = {r["sample_id"]: {"decision": "ALLOW"} for r in self.rows}
        for kept, removed in select_rows(self.rows, predictions, 3).values():
            self.assertEqual(kept, self.rows)
            self.assertEqual(removed, [])
