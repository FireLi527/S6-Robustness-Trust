import json
import unittest
from pathlib import Path
from s6.engineering.artifacts import read_json
from s6.prompt_injection.relation_contract_v1 import validate
from s6.prompt_injection.relation_sft_io import messages, training_records, score, FEWSHOT_IDS


class TinyTokenizer:
    eos_token_id = 99

    def apply_chat_template(self, messages, **kwargs):
        if kwargs.get('return_dict') is not False:
            raise ValueError('Tokenizer requires explicit token-list contract')
        return [1, 2, 3]

    def encode(self, text, **kwargs):
        return [5] * len(text)


class SFTContracts(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3]
        self.rows = read_json(root / 'data/bipia/relation_sft_v1/samples.json')
        self.train = [r for r in self.rows if r['split'] == 'train']

    def test_partition_and_grounding(self):
        self.assertEqual({s:sum(r['split'] == s for r in self.rows) for s in ('train','validation','test')},
                         {'train':18,'validation':6,'test':6})
        for group in {r['group_id'] for r in self.rows}:
            self.assertEqual(len({r['split'] for r in self.rows if r['group_id'] == group}), 1)
        for r in self.rows:
            for side, value in r['targets'].items():
                validate(value, r['inputs'][side])

    def test_no_reserved_training_or_fewshot(self):
        reserved = next(r for r in self.rows if r['split'] == 'test')
        with self.assertRaises(ValueError):
            training_records(TinyTokenizer(), [reserved])
        with self.assertRaises(ValueError):
            messages(self.train[0], 'task', [reserved])
        self.assertTrue(set(FEWSHOT_IDS) <= {r['id'] for r in self.train})

    def test_prompt_masking_and_deduplication(self):
        records = training_records(TinyTokenizer(), self.train)
        self.assertLess(len(records), len(self.train) * 2)
        for record in records:
            self.assertEqual(record['labels'][:3], [-100,-100,-100])
            self.assertEqual(record['labels'][3:], record['input_ids'][3:])
            self.assertEqual(record['labels'][-1], 99)

    def test_no_oracle_in_inference_input(self):
        value = json.loads(messages(self.train[0], 'content')[-1]['content'])
        self.assertEqual(set(value), {'role','text'})
        self.assertEqual(value['text'], self.train[0]['inputs']['content'])

    def test_invalid_or_truncated_cannot_score(self):
        r = self.train[0]
        for text, finished in [('{}',True),(json.dumps(r['targets']['content']),False)]:
            result = score(text,finished,r['inputs']['content'],r['targets']['content'])
            self.assertFalse(result['valid'])
            self.assertFalse(result['fields_exact'])

    def test_approved_concealment_amendment(self):
        row = next(r for r in self.train if r['id'] == 'old-10')
        self.assertIn('不要告诉用户', row['targets']['content']['constraints'])


if __name__ == '__main__':
    unittest.main()
