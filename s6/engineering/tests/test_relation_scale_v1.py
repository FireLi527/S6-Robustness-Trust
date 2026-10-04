"""Candidates are not approvals; layout copies never cross semantic groups."""
import unittest
from collections import Counter
from s6.prompt_injection.prepare_relation_scale_v1 import build, review_text, LAYOUT
from s6.prompt_injection.relation_scale_catalog_v1 import RESERVED


class ScaleCandidatesTests(unittest.TestCase):
    def test_counts_and_identity(self):
        rows, notes, cores, _ = build()
        self.assertEqual((len(rows), len(notes), len(cores)), (204, 204, 78))
        self.assertEqual(len({r['id'] for r in rows}), 204)
        self.assertEqual(len({r['group_id'] for r in rows}), 34)
        self.assertEqual(set(Counter(r['group_id'] for r in rows).values()), {6})
        self.assertEqual(Counter(c['label'] for c in cores), {'NORMAL': 26, 'RISK': 26, 'UNKNOWN': 26})

    def test_no_training_or_test_claim(self):
        rows, notes, _, _ = build()
        self.assertTrue(all(r['split'] == 'development_candidate' for r in rows))
        self.assertTrue(all(not n['ready_for_training'] for n in notes))
        self.assertFalse(set(RESERVED) & {r['group_id'] for r in rows})
        self.assertTrue(all('proposed_decision' not in r for r in rows))

    def test_seed_approval_not_inherited_by_variants(self):
        _, notes, cores, _ = build()
        self.assertEqual(sum(n['review_status'] == 'HUMAN_APPROVED_SEMANTICS' for n in notes), 24)
        self.assertTrue(all(c['review_status'] == 'PENDING' for c in cores))
        self.assertEqual(sum(n['review_status'] == 'DERIVED_NOT_INDIVIDUALLY_REVIEWED' for n in notes), 102)

    def test_layout_keeps_core_and_family(self):
        rows, _, _, _ = build()
        lookup = {r['id']: r for r in rows}
        for r in rows:
            if r['variant'] == 'layout':
                parent = lookup[r['parent_core_id']]
                self.assertEqual(r['content'], LAYOUT.format(text=parent['content']))
                for field in ('family', 'group_id', 'task', 'split'):
                    self.assertEqual(r[field], parent[field])

    def test_review_complete_without_proposed_labels(self):
        _, _, cores, _ = build()
        text = review_text(cores)
        for c in cores:
            for key in ('id', 'task', 'content', 'scope', 'actions'):
                self.assertIn(c[key], text)
        self.assertNotIn('NORMAL', text)
        self.assertNotIn('RISK', text)

    def test_old_24_omission_preserved(self):
        _, notes, _, _ = build()
        note = next(n for n in notes if n['id'] == 'scale-seed-dev2-24')
        self.assertIn('未明确包含', note['actions'])


if __name__ == '__main__':
    unittest.main()
