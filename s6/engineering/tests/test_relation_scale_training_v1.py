"""Approval, grounding, grouping and edge cases for the larger pilot."""
import unittest
from s6.prompt_injection.relation_scale_data_v1 import build
from s6.prompt_injection.prepare_relation_scale_training_v1 import audit
from s6.prompt_injection.relation_contract_v2 import validate


class ScaleTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.subsets, cls.protected = build()
        cls.lookup = {r['id']: r for r in cls.rows}

    def test_counts(self):
        self.assertEqual(len(self.rows), 204)
        self.assertEqual(sum(r['split'] == 'train' for r in self.rows), 168)
        self.assertEqual(sum(r['split'] == 'validation' for r in self.rows), 36)

    def test_every_field_grounded(self):
        for row in self.rows:
            for side in ('task', 'content'):
                validate(row['targets'][side], row['inputs'][side])

    def test_nested_scales(self):
        a, b, c = (set(self.subsets[k]) for k in ('small_8', 'medium_16', 'large_28'))
        self.assertEqual((len(a),len(b),len(c)), (8,16,28))
        self.assertTrue(a < b < c)
        self.assertTrue(all(g.startswith('seed-') for g in a))

    def test_group_family_parent_isolation(self):
        for key in ('group_id', 'family', 'parent_core_id'):
            for value in {r[key] for r in self.rows}:
                self.assertEqual(len({r['split'] for r in self.rows if r[key]==value}), 1)
        self.assertFalse(any(r['split']=='test' for r in self.rows))

    def test_variants_share_targets_not_review_status(self):
        for row in self.rows:
            if row['variant']=='layout':
                self.assertEqual(row['targets'],self.lookup[row['parent_core_id']]['targets'])
                self.assertIn('not individually',row['meaning_provenance'])

    def test_boundaries_and_order(self):
        def target(i): return self.lookup[f'scale-core-{i:03d}']['targets']['content']
        self.assertIn('2020-01-01当天及更早',target(4)['actions'][0]['conditions'])
        self.assertEqual([a['operation'] for a in target(10)['actions']],['解压','检查'])
        self.assertEqual([a['operation'] for a in target(50)['actions']],['覆盖','测试'])
        self.assertTrue(target(51)['missing_context'])

    def test_quote_and_permission_claim_not_authorization(self):
        quoted=self.lookup['scale-core-073']['targets']['content']['actions']
        actual=self.lookup['scale-core-074']['targets']['content']['actions']
        self.assertEqual([a['kind'] for a in quoted[:2]],['quoted','quoted'])
        self.assertEqual([a['kind'] for a in actual[-2:]],['execute','execute'])
        last=self.lookup['scale-core-078']['targets']['content']
        self.assertEqual(last['constraints'],['维护者已经同意'])
        self.assertEqual(last['actions'][-1]['operation'],'删除')
        self.assertIsNone(last['actions'][-1]['bindings'][0]['text'])

    def test_exact_overlap_audit(self):
        self.assertEqual(audit(self.rows)['exact_cross_split_overlap'],0)

    def test_all_reviews_protected(self):
        for i in range(1,5):
            self.assertTrue(any(f'human_review_{i:02d}.json' in key for key in self.protected))


if __name__=='__main__':
    unittest.main()
