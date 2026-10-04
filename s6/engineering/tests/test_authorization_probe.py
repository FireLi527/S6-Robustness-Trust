"""Synthetic-label visibility, input ablation and no-truncation contracts."""
import unittest
from s6.prompt_injection.authorization_probe import fixtures, pair_summary
from s6.prompt_injection.nli_authorization import nli_inputs, check_lengths


class AuthorizationProbeTests(unittest.TestCase):
    def test_exact_counterfactual_pairs(self):
        rows = fixtures()
        self.assertEqual(len(rows), 60)
        pairs = {r['pair_id'] for r in rows if r['pair_id'] is not None}
        self.assertEqual(len(pairs), 24)
        for identifier in pairs:
            pair = [r for r in rows if r['pair_id'] == identifier]
            self.assertEqual({r['label'] for r in pair}, {0, 1})
            self.assertEqual(len({r['content'] for r in pair}), 1)
            self.assertEqual(len({r['task'] for r in pair}), 2)

    def test_machine_labels_not_claimed_human(self):
        self.assertTrue(all('NOT human-reviewed' in r['label_basis'] for r in fixtures()))

    def test_task_ablation_removes_counterfactual_difference(self):
        a, b = fixtures()[:2]
        self.assertEqual(nli_inputs(a, 'task_ablated'), nli_inputs(b, 'task_ablated'))
        self.assertNotEqual(nli_inputs(a, 'conflict_hypothesis'), nli_inputs(b, 'conflict_hypothesis'))

    def test_unknown_formulation_rejected(self):
        with self.assertRaises(ValueError):
            nli_inputs(fixtures()[0], 'unregistered')

    def test_input_limit_rejects_instead_of_truncating(self):
        check_lengths([512], 512)
        with self.assertRaises(ValueError):
            check_lengths([513], 512)

    def test_both_correct_not_just_ordering(self):
        rows = [{**r, 'score': .2 + .1*r['label'], 'flag': False} for r in fixtures()[:2]]
        result = pair_summary(rows)
        self.assertEqual(result['risk_score_higher'], 1)
        self.assertEqual(result['both_correct'], 0)

    def test_ties_counted(self):
        rows = [{**r, 'score': .2, 'flag': False} for r in fixtures()[:2]]
        self.assertEqual(pair_summary(rows)['score_ties'], 1)

    def test_pair_missing_member_rejected(self):
        with self.assertRaises(ValueError):
            pair_summary([{**fixtures()[0], 'score': .2, 'flag': False}])
