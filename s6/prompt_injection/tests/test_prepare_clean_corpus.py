from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from prepare_clean_corpus import assign_and_sample, format_record, load_sent_mail


class LoadSentMailTests(unittest.TestCase):
    def test_filters_by_folder_length_and_dedup(self) -> None:
        rows = [
            # kept: in _sent_mail, in-range length
            {"file_name": "alice/_sent_mail/1.", "body": "x" * 100, "message_id": "1",
             "subject": "s", "from": "alice@enron.com", "date": pd.Timestamp("2001-01-01")},
            # dropped: not in _sent_mail
            {"file_name": "alice/inbox/2.", "body": "y" * 100, "message_id": "2",
             "subject": "s", "from": "alice@enron.com", "date": pd.Timestamp("2001-01-01")},
            # dropped: too short
            {"file_name": "alice/_sent_mail/3.", "body": "short", "message_id": "3",
             "subject": "s", "from": "alice@enron.com", "date": pd.Timestamp("2001-01-01")},
            # dropped: too long
            {"file_name": "alice/_sent_mail/4.", "body": "z" * 5000, "message_id": "4",
             "subject": "s", "from": "alice@enron.com", "date": pd.Timestamp("2001-01-01")},
            # dropped: exact-duplicate body of row 1
            {"file_name": "bob/_sent_mail/5.", "body": "x" * 100, "message_id": "5",
             "subject": "s", "from": "bob@enron.com", "date": pd.Timestamp("2001-01-01")},
        ]
        frame = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = Path(tmp) / "shard.parquet"
            frame.to_parquet(parquet_path)
            result = load_sent_mail(parquet_path, min_length=60, max_length=4000)
        self.assertEqual(list(result["message_id"]), ["1"])
        self.assertEqual(list(result["custodian"]), ["alice"])


class AssignAndSampleTests(unittest.TestCase):
    def _fixture(self) -> pd.DataFrame:
        rows = []
        for custodian_index in range(6):
            for message_index in range(15):
                rows.append(
                    {
                        "custodian": f"custodian{custodian_index}",
                        "message_id": f"{custodian_index}-{message_index}",
                        "subject": "s",
                        "from": f"custodian{custodian_index}@enron.com",
                        "date": pd.Timestamp("2001-01-01"),
                        "body": "body text",
                        "file_name": f"custodian{custodian_index}/_sent_mail/{message_index}.",
                    }
                )
        return pd.DataFrame(rows)

    def test_splits_are_custodian_disjoint_and_reach_target(self) -> None:
        frame = self._fixture()
        splits = assign_and_sample(frame, seed=2023, per_split_count=20, per_custodian_cap=10)
        development_custodians = set(splits["development"]["custodian"])
        unseen_custodians = set(splits["unseen_test"]["custodian"])
        self.assertFalse(development_custodians & unseen_custodians)
        self.assertEqual(len(splits["development"]), 20)
        self.assertEqual(len(splits["unseen_test"]), 20)

    def test_deterministic_for_fixed_seed(self) -> None:
        frame = self._fixture()
        first = assign_and_sample(frame, seed=2023, per_split_count=20, per_custodian_cap=10)
        second = assign_and_sample(frame, seed=2023, per_split_count=20, per_custodian_cap=10)
        self.assertEqual(
            list(first["development"]["message_id"]), list(second["development"]["message_id"])
        )
        self.assertEqual(
            list(first["unseen_test"]["message_id"]), list(second["unseen_test"]["message_id"])
        )

    def test_raises_when_pool_too_small(self) -> None:
        frame = self._fixture()
        with self.assertRaises(ValueError):
            assign_and_sample(frame, seed=2023, per_split_count=1000, per_custodian_cap=10)


class FormatRecordTests(unittest.TestCase):
    def test_matches_bipia_context_template(self) -> None:
        row = pd.Series(
            {
                "subject": "Hello",
                "from": "alice@enron.com",
                "date": pd.Timestamp("2001-01-01"),
                "body": "Body text.",
                "message_id": "1",
                "custodian": "alice",
                "file_name": "alice/_sent_mail/1.",
            }
        )
        record = format_record(row)
        self.assertEqual(
            record["context"],
            "SUBJECT: Hello|EMAIL_FROM: alice@enron.com|RECEIVED DATE: "
            "2001-01-01 00:00:00|CONTENT: \n\nBody text.",
        )
        self.assertEqual(record["question"], "")
        self.assertEqual(record["source"], "corbt/enron-emails")


if __name__ == "__main__":
    unittest.main()
