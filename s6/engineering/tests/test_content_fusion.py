"""Decision fusion must not convert disagreement or invalid evidence into agreement."""
import unittest
from s6.prompt_injection.content_fusion_v1 import fuse_decisions
from s6.prompt_injection.content_reviewer_runtime_v1 import review_batch


class FusionContractTests(unittest.TestCase):
    def test_union_preserves_detector_rescue_when_review_is_invalid(self):
        self.assertEqual(fuse_decisions('RISK','INVALID','union'),'RISK')
        self.assertEqual(fuse_decisions('NORMAL','INVALID','union'),'UNKNOWN')

    def test_consensus_requires_two_valid_decisions(self):
        for a,b in [('NORMAL','RISK'),('RISK','NORMAL'),('NORMAL','UNKNOWN'),('INVALID','INVALID')]:
            self.assertEqual(fuse_decisions(a,b,'consensus'),'UNKNOWN')
        self.assertEqual(fuse_decisions('NORMAL','NORMAL','consensus'),'NORMAL')
        self.assertEqual(fuse_decisions('RISK','RISK','consensus'),'RISK')

    def test_unknown_is_not_normal(self):
        self.assertEqual(fuse_decisions('NORMAL','UNKNOWN','union'),'UNKNOWN')
        self.assertEqual(fuse_decisions('UNKNOWN','RISK','union'),'RISK')

    def test_invalid_component_or_policy_rejected(self):
        with self.assertRaises(ValueError):
            fuse_decisions('SAFE','NORMAL','union')
        with self.assertRaises(ValueError):
            fuse_decisions('NORMAL','NORMAL','average')

    def test_missing_trusted_task_never_becomes_inferred_authorization(self):
        with self.assertRaises(ValueError):
            review_batch(None,None,[{'task':None}],{})

    def test_batch_resource_limit_rejects_before_model_use(self):
        with self.assertRaises(ValueError):
            review_batch(None,None,[{}]*5,{})

    def test_over_budget_preserves_full_input_without_model_use(self):
        class Tokenizer:
            def apply_chat_template(self,*args,**kwargs):
                return [1,2,3,4,5,6]
        row = {'id':'budget','task':'Explain this text','content':'Quoted data',
               'source':'contract','expected':'NORMAL'}
        result = review_batch(None,Tokenizer(),[row],{'prompt':'review','max_new_tokens':2,'total_budget':7})[0]
        self.assertEqual(result['input_ids'],[1,2,3,4,5,6])
        self.assertEqual(result['decision'],'INVALID')
        self.assertEqual(result['generated_token_ids'],[])
