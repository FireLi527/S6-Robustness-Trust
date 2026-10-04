import copy
import unittest
from s6.prompt_injection.repository_scope_review import build, validate, review_markdown


class ReviewContracts(unittest.TestCase):
    def test_groups_and_pending(self):
        rows, annotations = build()
        self.assertEqual({s: sum(r['split'] == s for r in rows) for s in {r['split'] for r in rows}},
                         {'train_seed': 12, 'validation_reserved': 6, 'test_reserved': 6})
        self.assertEqual(len({r['group_id'] for r in rows}), 12)
        self.assertTrue(all(not p['training_eligible'] for p in annotations))
        self.assertNotIn('label', rows[0])

    def test_no_implicit_approval(self):
        rows, annotations = build()
        for key, value in [('human_status', 'APPROVED'), ('human_decision', 'NORMAL'), ('human_slots_approved', True), ('training_eligible', True)]:
            changed = copy.deepcopy(annotations)
            changed[0][key] = value
            with self.assertRaises(ValueError):
                validate(rows, changed)

    def test_group_leak_rejected(self):
        rows, annotations = build()
        rows[0]['split'] = 'different'
        with self.assertRaises(ValueError):
            validate(rows, annotations)

    def test_review_preserves_text(self):
        rows, annotations = build()
        document = review_markdown(rows, annotations)
        for r in rows:
            self.assertIn(r['task'], document)
            self.assertIn(r['content'], document)
        self.assertNotIn('proposed_decision', document)

    def test_unknown_retained(self):
        _, annotations = build()
        self.assertEqual(sum(p['proposed_decision'] == 'UNKNOWN' for p in annotations), 4)


if __name__ == '__main__':
    unittest.main()
