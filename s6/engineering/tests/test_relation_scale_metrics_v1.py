"""Evaluation coverage and denominator contracts without model execution."""
import copy
import json
from pathlib import Path
import unittest
from s6.prompt_injection.relation_scale_metrics_v1 import ARMS, coverage, jobs, summarize
from s6.prompt_injection.relation_sft_v2_io import score_text, messages


class ScaleEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[3] / 'data/bipia/relation_scale_training_v1/samples.json'
        cls.rows = [r for r in json.loads(path.read_text(encoding='utf-8')) if r['split'] == 'validation']

    def predictions(self):
        return [{'id': r['id'], 'side': s, 'arm': a, 'text': json.dumps(r['targets'][s]), 'finished': True,
                 'score': score_text(json.dumps(r['targets'][s]), True, r['inputs'][s], r['targets'][s])}
                for a in ARMS for r in self.rows for s in ('task', 'content')]

    def test_unique_counts(self):
        self.assertEqual(len(jobs(self.rows)), 42)
        self.assertEqual(len(jobs([r for r in self.rows if r['variant'] == 'core'])), 24)

    def test_train_rejected(self):
        row = copy.deepcopy(self.rows[0]); row['split'] = 'train'
        with self.assertRaises(ValueError):
            jobs([row])

    def test_conflicting_target_rejected(self):
        row = copy.deepcopy(self.rows[0]); row['targets']['task']['constraints'] = []
        with self.assertRaises(ValueError):
            jobs([self.rows[0], row])

    def test_coverage_rejects_missing(self):
        with self.assertRaises(ValueError):
            coverage(self.predictions()[:-1], self.rows)

    def test_coverage_rejects_duplicate(self):
        predictions = self.predictions()
        with self.assertRaises(ValueError):
            coverage(predictions + predictions[:1], self.rows)

    def test_denominators(self):
        result = summarize(self.predictions(), self.rows)
        for arm in ARMS:
            self.assertEqual(result[arm]['all']['both_exact'], 36)
            self.assertEqual(result[arm]['all']['unique_exact'], 42)
            self.assertEqual(result[arm]['core']['both_exact'], 18)
            self.assertEqual(result[arm]['core']['by_side']['task']['n'], 6)
            self.assertEqual(result[arm]['core']['by_side']['content']['n'], 18)
            self.assertEqual(result[arm]['layout']['unique_sides'], 24)

    def test_failed_outputs_still_count(self):
        predictions = self.predictions()
        for p in predictions:
            r = next(r for r in self.rows if r['id'] == p['id'])
            p.update(text='', finished=False, score=score_text('', False, r['inputs'][p['side']], r['targets'][p['side']]))
        result = summarize(predictions, self.rows)['large_28']['all']
        self.assertEqual(result['unique_unfinished'], 42)
        self.assertEqual(result['both_exact'], 0)
        self.assertIsNone(result['strict_units']['precision'])
        self.assertEqual(result['strict_units']['recall'], 0)

    def test_no_other_side_in_request(self):
        row = self.rows[0]
        request = json.loads(messages(row, 'content')[-1]['content'])
        self.assertEqual(request, {'role': 'content', 'text': row['inputs']['content']})


if __name__ == '__main__':
    unittest.main()
