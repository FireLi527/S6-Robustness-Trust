import copy
import unittest
from pathlib import Path
from s6.engineering.artifacts import read_json
from s6.prompt_injection.relation_contract_v1 import validate, validate_target, source_span
from s6.prompt_injection.relation_seed_conversion_v1 import convert


class RelationContractTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3]
        self.rows = read_json(root / 'data/bipia/repository_scope_approved_v1/annotations.json')
        self.train = [r for r in self.rows if r['split'] == 'train_seed']

    def test_conversions_grounded(self):
        rows = convert(self.train)
        self.assertEqual(len(rows), 12)
        for row in rows:
            for side, value in row['targets'].items():
                self.assertFalse(validate(value, row['inputs'][side])['semantic_correctness_verified'])

    def test_reserved_input_rejected(self):
        with self.assertRaises(ValueError):
            convert(self.rows)

    def test_quote_and_unknown_preserved(self):
        rows = {r['id']: r for r in convert(self.train)}
        self.assertTrue(all(a['kind'] == 'quoted' for a in rows[9]['targets']['content']['actions']))
        self.assertEqual(rows[16]['targets']['content']['actions'][0]['targets'][0]['status'], 'unmapped')
        self.assertEqual(rows[21]['targets']['task']['mode'], 'unknown')
        self.assertEqual(rows[21]['targets']['content']['actions'][0]['targets'][0]['mention'], 'exports/result.json')

    def test_invented_evidence_rejected(self):
        row = convert(self.train)[0]
        value = copy.deepcopy(row['targets']['content'])
        value['actions'][0]['evidence'] = 'invented'
        with self.assertRaises(ValueError):
            validate(value, row['inputs']['content'])

    def test_unknown_cannot_be_filled(self):
        with self.assertRaises(ValueError):
            validate_target({'mention': 'blue', 'status': 'unmapped', 'candidates': ['staging']}, 'blue staging', 'blue')

    def test_ambiguous_requires_candidates(self):
        validate_target({'mention': '它', 'status': 'ambiguous', 'candidates': ['甲', '乙']}, '甲乙它', '它')
        with self.assertRaises(ValueError):
            validate_target({'mention': '它', 'status': 'ambiguous', 'candidates': ['甲']}, '甲乙它', '它')

    def test_exact_unicode_offsets(self):
        self.assertEqual(source_span('中文证据', '证据'), {'text': '证据', 'start': 2, 'end': 4})


if __name__ == '__main__':
    unittest.main()
