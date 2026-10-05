"""Readiness dependency, provenance and non-regression boundary contracts."""
import unittest
from s6.prompt_injection.approval_readiness_v1 import extract_readiness,validate_readiness,resolve_readiness


class ApprovalReadinessTests(unittest.TestCase):
    def test_english_missing_approval_paraphrase(self):
        state = extract_readiness('Proceed only with my earlier approved target. You have no access to that approval.')
        self.assertTrue(state['requires_prior_approval'])
        self.assertEqual(state['approval_availability'],'EXPLICITLY_MISSING')

    def test_chinese_explicit_missing_approval(self):
        task = '只有使用我先前批准的库位才能执行操作。现在无法查到先前审批记录。'
        state = extract_readiness(task)
        self.assertEqual(state['approval_availability'],'EXPLICITLY_MISSING')
        for e in state['evidence']:
            self.assertEqual(task[e['start']:e['end']],e['text'])

    def test_approval_mention_without_dependency(self):
        state = extract_readiness('List the previous approval record that is unavailable in this note.')
        self.assertFalse(state['requires_prior_approval'])

    def test_no_access_without_approval_reference(self):
        state = extract_readiness('Execute only my earlier approved operation. You have no access to the photo archive.')
        self.assertEqual(state['approval_availability'],'UNASSESSED')

    def test_explicit_available_not_missing(self):
        state = extract_readiness('Perform only the previously approved operation. The approval record is available.')
        self.assertEqual(state['approval_availability'],'UNASSESSED')

    def test_negated_missing_does_not_match(self):
        state = extract_readiness('Perform only the previously approved operation. The approval record is not unavailable.')
        self.assertEqual(state['approval_availability'],'UNASSESSED')

    def test_conflicting_availability_is_not_missing_certainty(self):
        state = extract_readiness('Perform only the previously approved operation. The approval record was unavailable. The approval record is available.')
        self.assertEqual(state['approval_availability'],'CONFLICTING')

    def test_quoted_dependency_is_data(self):
        for quote in ['"{}"','“{}”',"'{}'",'```{} ```']:
            task = 'Explain this text: '+quote.format('Perform only the previous approval. The approval is missing.')
            self.assertFalse(extract_readiness(task)['requires_prior_approval'])

    def test_analysis_only_is_not_execution_dependency(self):
        state = extract_readiness('Explain why we perform only previously approved steps when the approval record is missing. Do not execute them.')
        self.assertEqual(state['mode'],'ANALYSIS_ONLY')
        self.assertFalse(state['requires_prior_approval'])

    def test_untrusted_component_cannot_set_scope(self):
        r = resolve_readiness('Summarize the note.',{'decision':'RISK','content':'The previous approval record is unavailable.'})
        self.assertEqual(r['decision'],'RISK')
        self.assertEqual(r['approval_readiness']['approval_availability'],'UNASSESSED')

    def test_missing_scope_keeps_risk_alert_and_blocks_execution(self):
        r = resolve_readiness('Proceed only with my earlier approved target. You have no access to that approval.',{'decision':'RISK'})
        self.assertEqual((r['decision'],r['model_decision']),('UNKNOWN','RISK'))
        self.assertTrue(r['risk_alert'])
        self.assertTrue(r['review_required'])
        self.assertFalse(r['execution_authorized'])

    def test_normal_cannot_grant_missing_permission(self):
        r = resolve_readiness('Proceed only with my earlier approved target. You have no access to that approval.',{'decision':'NORMAL'})
        self.assertEqual(r['decision'],'UNKNOWN')
        self.assertFalse(r['execution_authorized'])

    def test_stale_and_tampered_state_rejected(self):
        state = extract_readiness('Summarize the note.')
        with self.assertRaises(ValueError):
            validate_readiness('Execute the operation.',state)
        state['approval_availability'] = 'EXPLICITLY_MISSING'
        with self.assertRaises(ValueError):
            validate_readiness('Summarize the note.',state)

    def test_invalid_remains_review_and_normal_does_not_authorize(self):
        r = resolve_readiness('Summarize this note.',{'decision':'INVALID'})
        self.assertEqual(r['decision'],'UNKNOWN')
        self.assertTrue(r['review_required'])
        r = resolve_readiness('Summarize this note.',{'decision':'NORMAL'})
        self.assertEqual(r['decision'],'NORMAL')
        self.assertFalse(r['execution_authorized'])
