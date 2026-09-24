import importlib.util
import unittest
if importlib.util.find_spec('tensorboard') is None:
    raise unittest.SkipTest('Training checks require WSL s6-training environment')
from copy import deepcopy
from pathlib import Path
from prepare_fruitfly import RESULTS,DATA
from prepare_fruitfly_grouped_defense import read
from train_fruitfly_defense import verify_run

class ResumeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths=list((RESULTS/'model_training/clean_subset').glob('*/summary.json'))
        if not paths:raise unittest.SkipTest('Requires local verified fruitfly baseline')
        cls.base=read(paths[0])
        if not Path(cls.base['checkpoint']).exists():raise unittest.SkipTest('Requires WSL checkpoint path')

    def test_reuses_matching_completed_baseline(self):
        verify_run(self.base,self.base,DATA/'manifests/clean_subset.csv',6531)

    def test_changed_hyperparameters_rejected_even_with_old_hash(self):
        modified=deepcopy(self.base);modified['protocol']['epochs']=10
        with self.assertRaisesRegex(ValueError,'Hyperparameters changed'):
            verify_run(modified,self.base,DATA/'manifests/clean_subset.csv',6531)

    def test_changed_sample_count_rejected(self):
        with self.assertRaisesRegex(ValueError,'Training sample count mismatch'):
            verify_run(self.base,self.base,DATA/'manifests/clean_subset.csv',6000)
