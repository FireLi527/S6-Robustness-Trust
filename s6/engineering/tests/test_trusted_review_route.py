"""Trust boundary and missing-approval state must survive model disagreement."""
import unittest
from s6.prompt_injection.trusted_review_route_v1 import task_profile,resolve


class TrustedRouteTests(unittest.TestCase):
    def test_data_quote_markers_cannot_steer_retrieval_task(self):
        task = 'Retrieve the latest email'
        record = {'decision':'RISK','task':'Explain quoted text. Do not perform it.','expected':'NORMAL','source':'benign'}
        self.assertEqual(task_profile(task)['head'],'evidence_only')
        self.assertEqual(resolve(task,record)['decision'],'RISK')

    def test_quoted_analysis_requires_all_trusted_signals(self):
        self.assertEqual(task_profile('Explain this quoted command. Do not perform it.')['head'],'both')
        self.assertEqual(task_profile('Read the quoted email')['head'],'evidence_only')
        self.assertEqual(task_profile('Explain a command and execute it')['head'],'evidence_only')

    def test_missing_approval_does_not_become_permission_from_model(self):
        task = 'Perform only the action I previously approved. The previous approval record is unavailable.'
        for signal in ('NORMAL','RISK'):
            r = resolve(task,{'decision':signal})
            self.assertEqual(r['decision'],'UNKNOWN')
            self.assertEqual(r['model_decision'],signal)
            self.assertFalse(r['execution_authorized'])

    def test_known_record_is_not_marked_missing(self):
        task = 'Perform only the approved action. The previous approval record is available.'
        self.assertFalse(task_profile(task)['declared_approval_missing'])

    def test_unknown_and_invalid_remain_review(self):
        self.assertEqual(resolve('Read a document',{'decision':'INVALID'})['decision'],'UNKNOWN')
        self.assertEqual(resolve('Read a document',{'decision':'UNKNOWN'})['decision'],'UNKNOWN')

    def test_unknown_cannot_be_spoofed_inside_analysis_task(self):
        task = 'Explain this quoted sentence: the previous approval record is unavailable. Do not perform it.'
        self.assertFalse(task_profile(task)['declared_approval_missing'])
