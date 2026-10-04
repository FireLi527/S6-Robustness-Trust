import unittest
import numpy as np
from train_repo_file_v2_development import select_by_source


class PerSourceThresholdTests(unittest.TestCase):
    def test_one_source_cannot_hide_another_sources_false_positives(self):
        y=np.array([1]+[0]*100+[1]+[0]*10)
        scores=np.array([.99]+[.1]*100+[.98,.9]+[.1]*9)
        sources=['a']*101+['b']*11
        threshold,metrics=select_by_source(y,scores,sources)
        self.assertGreater(threshold,.9)
        self.assertEqual(metrics['b']['fpr'],0)
        self.assertEqual(metrics['a']['recall'],1)

    def test_reject_all_is_valid_when_tied_scores_cannot_meet_constraint(self):
        threshold,metrics=select_by_source(np.array([0,1,0,1]),np.array([.5]*4),['a','a','b','b'])
        self.assertGreater(threshold,.5)
        self.assertEqual(metrics['a']['recall'],0)
        self.assertEqual(metrics['b']['fpr'],0)


if __name__=='__main__':
    unittest.main()
