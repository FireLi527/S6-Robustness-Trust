import copy
import unittest
from pathlib import Path
from s6.engineering.artifacts import read_json
from s6.prompt_injection.finalize_repository_scope_review import assemble

ROOT = Path(__file__).resolve().parents[3]


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.rows = read_json(ROOT / 'data/bipia/repository_scope_review_v1/inputs.json')
        self.proposals = read_json(ROOT / 'data/bipia/repository_scope_review_v1/assistant_proposals.json')
        self.review = read_json(ROOT / 'data/bipia/repository_scope_human_review_v1/review.json')
        self.confirmation = read_json(ROOT / 'data/bipia/repository_scope_human_review_v1/field_confirmation.json')

    def test_approved_text_preserved_without_sft_claim(self):
        result = assemble(self.rows, self.proposals, self.review, self.confirmation)
        for row, proposal, actual in zip(self.rows, self.proposals, result):
            self.assertEqual(actual['split'], row['split'])
            self.assertEqual(actual['approved_content_actions'], proposal['content_actions'])
            self.assertEqual(actual['approved_task_scope'], proposal['task_scope'])
            self.assertFalse(actual['ready_for_sft'])
            self.assertNotIn('task_mode', actual)
        self.assertEqual([r['id'] for r in result if r['human_decision'] == 'UNKNOWN'], [12, 16, 21, 22])
        self.assertIn('引用', result[8]['approved_content_actions'])

    def test_missing_or_duplicate_approval_rejected(self):
        for ids in [list(range(1, 24)), list(range(1, 24)) + [23]]:
            changed = copy.deepcopy(self.confirmation)
            changed['approved_ids'] = ids
            with self.assertRaises(ValueError):
                assemble(self.rows, self.proposals, self.review, changed)

    def test_unapproved_field_rejected(self):
        changed = copy.deepcopy(self.confirmation)
        changed['approved_fields'].append('task_mode')
        with self.assertRaises(ValueError):
            assemble(self.rows, self.proposals, self.review, changed)


if __name__ == '__main__':
    unittest.main()
