import unittest

import numpy as np

from train_repo_file_v1 import confusion, select_threshold


class RepoFileV1Tests(unittest.TestCase):
    def test_confusion_keeps_precision_recall_fpr_separate(self):
        metrics = confusion(np.array([1, 1, 0, 0]), np.array([True, False, True, False]))
        self.assertEqual((metrics["tp"], metrics["fn"], metrics["fp"], metrics["tn"]), (1, 1, 1, 1))
        self.assertEqual(metrics["precision"], .5)
        self.assertEqual(metrics["recall"], .5)
        self.assertEqual(metrics["fpr"], .5)

    def test_threshold_respects_five_percent_clean_fpr(self):
        labels = np.array([1, 1] + [0] * 20)
        scores = np.array([.9, .7, .8] + [.1] * 19)
        threshold, metrics = select_threshold(labels, scores)
        self.assertEqual(threshold, .7)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["fpr"], .05)


if __name__ == "__main__":
    unittest.main()
