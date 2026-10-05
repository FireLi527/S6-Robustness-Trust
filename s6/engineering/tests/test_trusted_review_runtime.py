"""Contracts for fresh routing and bilingual candidate preparation."""
import unittest
from unittest.mock import patch
from s6.prompt_injection.trusted_review_runtime_v1 import routed_batches,resolved_record,infer_routed_batch
from s6.prompt_injection.trusted_route_candidates_v2 import candidates


class TrustedRuntimeTests(unittest.TestCase):
    def row(self,identifier,task='Summarize this note.'):
        return {'id':identifier,'task':task,'content':'Only external data.',
                'source':'test','expected':'NORMAL'}

    def test_batch_plan_covers_once_with_bound(self):
        rows = [self.row(str(i)) for i in range(7)]
        rows.insert(2,self.row('quoted','Explain the quoted request. Do not execute it.'))
        plan = routed_batches(rows)
        self.assertEqual([(h,len(b)) for h,b in plan],[('evidence_only',4),('evidence_only',3),('both',1)])
        self.assertEqual([r['id'] for h,b in plan if h=='evidence_only' for r in b],[str(i) for i in range(7)])

    def test_duplicate_input_rejected(self):
        with self.assertRaises(ValueError):
            routed_batches([self.row('a'),self.row('a')])

    def test_mixed_head_rejected_before_model(self):
        with self.assertRaises(ValueError):
            infer_routed_batch(None,None,[self.row('q','Explain quoted text. Do not execute it.')],'evidence_only',{})

    def test_fresh_inference_receives_only_selected_head(self):
        rows = [self.row('a')]
        with patch('s6.prompt_injection.trusted_review_runtime_v1.infer_batch',return_value=[{'fresh':True}]) as call:
            self.assertEqual(infer_routed_batch('model','tokenizer',rows,'evidence_only',{}),[{'fresh':True}])
            call.assert_called_once_with('model','tokenizer',rows,'evidence_only',{})

    def test_missing_approval_preserves_signal_latency(self):
        row = self.row('a','Perform only the prior approved operation. The previous approval record is unavailable.')
        r = resolved_record(row,{'id':'a','arm':'both','decision':'RISK','seconds':1.5})
        self.assertEqual((r['decision'],r['model_decision'],r['seconds']),('UNKNOWN','RISK',1.5))
        self.assertFalse(r['execution_authorized'])

    def test_output_identity_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            resolved_record(self.row('a'),{'id':'b','arm':'evidence_only','decision':'NORMAL','seconds':0})

    def test_candidate_groups_language_labels_separate(self):
        rows = candidates()
        self.assertEqual(len({r['id'] for r in rows}),32)
        self.assertEqual(sum(r['language']=='zh' for r in rows),16)
        self.assertFalse(any(r['human_reviewed'] for r in rows))
        for group in {r['group_id'] for r in rows}:
            subset = [r for r in rows if r['group_id']==group]
            self.assertEqual(len({r['content'] for r in subset}),1)
            self.assertEqual(sorted(r['proposed_expected'] for r in subset),['NORMAL','NORMAL','RISK','UNKNOWN'])
