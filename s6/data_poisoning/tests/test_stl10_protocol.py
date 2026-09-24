import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import dataset_config
from prepare_stl10_poisoning import split_train
from semantic_detector import detector_metadata

class STL10ProtocolTests(unittest.TestCase):
    def test_split_is_stratified_disjoint_and_reproducible(self):
        labels = np.repeat(np.arange(10), 500)
        train, val = split_train(labels)
        self.assertFalse(train & val)
        self.assertEqual(train | val, set(range(5000)))
        self.assertEqual((train, val), split_train(labels))
        for label in range(10):
            self.assertEqual(sum(labels[i] == label for i in train), 400)
            self.assertEqual(sum(labels[i] == label for i in val), 100)

    def test_results_reject_changed_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "clean_subset.csv"
            path.write_text("before")
            with patch.object(dataset_config, "MANIFEST_ROOT", root):
                payload = {"detector": detector_metadata(), "manifest_hashes": dataset_config.manifest_hashes()}
                self.assertTrue(dataset_config.evaluation_matches(payload))
                path.write_text("after")
                self.assertFalse(dataset_config.evaluation_matches(payload))
