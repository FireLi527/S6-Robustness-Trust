from __future__ import annotations

import unittest

from prepare_splits import build_split_manifests


class SplitManifestTests(unittest.TestCase):
    def test_shared_categories_are_excluded_from_development(self) -> None:
        development, unseen = build_split_manifests(
            {
                "Development only": ["first development attack"],
                "Shared": ["development version"],
            },
            {
                "Shared": ["test version"],
                "Test only": ["first test attack", "second test attack"],
            },
        )
        self.assertEqual(development["categories"], ["Development only"])
        self.assertEqual(unseen["categories"], ["Shared", "Test only"])
        self.assertEqual(development["excluded_overlapping_categories"], ["Shared"])
        self.assertFalse(set(development["categories"]) & set(unseen["categories"]))
        self.assertEqual(len(development["attacks"]), 1)
        self.assertEqual(len(unseen["attacks"]), 3)

    def test_manifest_does_not_store_attack_text(self) -> None:
        development, _ = build_split_manifests(
            {"Development": ["sensitive test instruction"]},
            {"Unseen": ["other instruction"]},
        )
        serialized = str(development)
        self.assertNotIn("sensitive test instruction", serialized)
        self.assertIn("attack_text_sha256", serialized)


if __name__ == "__main__":
    unittest.main()
