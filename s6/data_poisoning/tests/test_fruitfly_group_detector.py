import unittest
from dataclasses import fields
import numpy as np
from fruitfly_group_detector import GroupedInput,fold_indices,signals,decisions,group_id

class GroupedDetectorTests(unittest.TestCase):
    def fixture(self):
        rng=np.random.default_rng(3);records=[];embeddings={}
        for group in range(20):
            for view in range(2):
                sid=f'{group}_{view}';label=str(group%2)
                vector=np.array([1.,0.,0.,0.]) if label=='0' else np.array([0.,1.,0.,0.])
                embeddings[sid]=vector+rng.normal(0,.01,4)
                records.append(GroupedInput(sid,sid,label,f'g{group}'))
        return records,embeddings

    def test_all_views_of_specimen_are_held_out_together(self):
        records,_=self.fixture();groups=[r.group_id for r in records];seen=[]
        for train,test in fold_indices(groups):
            self.assertFalse({groups[i] for i in train}&{groups[i] for i in test})
            seen.extend(test)
        self.assertEqual(sorted(seen),list(range(len(records))))

    def test_other_held_out_labels_do_not_affect_sample_signals(self):
        records,embeddings=self.fixture();first,folds=signals(records,embeddings)
        target=0;other=next(i for i in range(1,len(records)) if folds[i]==folds[target])
        altered=list(records);r=altered[other]
        altered[other]=GroupedInput(r.sample_id,r.sha256,'1' if r.assigned_label=='0' else '0',r.group_id)
        second,_=signals(altered,embeddings)
        np.testing.assert_allclose(first[target],second[target],atol=1e-10)

    def test_inputs_exclude_truth_and_duplicate_rejected(self):
        self.assertEqual({f.name for f in fields(GroupedInput)},{'sample_id','sha256','assigned_label','group_id'})
        records,embeddings=self.fixture()
        with self.assertRaises(ValueError):signals(records+[records[0]],embeddings)
        self.assertEqual(group_id('021001001111101_1.jpg'),group_id('021001001111102_1.jpg'))

    def test_fixed_threshold_decisions(self):
        records,_=self.fixture()
        results=decisions(records[:2],np.array([[0,0,0],[1,1,1]]),[.4,.4,.2],.62)
        self.assertEqual(results[records[0].sample_id]['decision'],'ALLOW')
        self.assertEqual(results[records[1].sample_id]['decision'],'REVIEW')
