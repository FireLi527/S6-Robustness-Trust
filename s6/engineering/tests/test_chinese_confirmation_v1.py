"""New-material boundary and review-before-inference contracts."""
from pathlib import Path
import subprocess
import sys
import unittest
from s6.engineering.artifacts import read_json,require_hash
from s6.prompt_injection.chinese_analysis_v3 import task_profile

ROOT = Path(__file__).resolve().parents[3]
MATERIAL = ROOT/'data/bipia/chinese_analysis_confirmation_candidates_v1_compat'


class ChineseConfirmationV1Tests(unittest.TestCase):
    def test_integrity_and_new_topics(self):
        for name,digest in read_json(MATERIAL/'integrity.json').items():
            require_hash(MATERIAL/name,digest)
        rows = read_json(MATERIAL/'candidates.json')
        old = read_json(ROOT/'data/bipia/readiness_routing_v3/rows.json')
        self.assertEqual(len(rows),40)
        self.assertEqual(len({r['id'] for r in rows}),40)
        self.assertFalse({r['content'] for r in rows}&{r['content'] for r in old})
        self.assertFalse({r['group_id'] for r in rows}&{r.get('group_id') for r in old})

    def test_attack_and_normal_both_enter_chinese_head(self):
        for row in read_json(MATERIAL/'candidates.json'):
            head = task_profile(row['task'])['head']
            if row['variant'] in {'quote','analysis_hijack'}:
                self.assertEqual(head,'zh_analysis')
            else:
                self.assertNotEqual(head,'zh_analysis')

    def test_no_model_scores_in_material(self):
        for row in read_json(MATERIAL/'candidates.json'):
            self.assertFalse(row['human_reviewed'])
            self.assertNotIn('expected',row)
            self.assertNotIn('decision',row)

    def test_prepare_requires_direct_review(self):
        review = ROOT/'data/bipia/chinese_analysis_confirmation_review_v1/human_review.json'
        if review.exists():
            self.skipTest('Direct review now present; preparation gate was checked before review')
        proc = subprocess.run([sys.executable,'-m','s6.prompt_injection.experiment_chinese_analysis_confirmation_v1','--stage','prepare'],
                              cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(proc.returncode,0)
        self.assertIn('human_review.json',proc.stderr)
        self.assertFalse((ROOT/'data/bipia/chinese_analysis_confirmation_v1').exists())
