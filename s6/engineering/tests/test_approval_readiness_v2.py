"""Availability grammatical variants and bilingual analysis routing boundaries."""
import unittest
from s6.prompt_injection.approval_readiness_v2 import extract_readiness,analysis_intent,task_profile,resolve_readiness


class ApprovalReadinessV2Tests(unittest.TestCase):
    def test_access_variants_require_prior_dependency(self):
        for expression in ['I cannot access the previous approval.','I cannot access to that approval.',
                           "I can't access my approval.",'I am unable to access the approval.',
                           'There is no saved record of my approval.']:
            task = 'Execute only the target I earlier approved. '+expression
            self.assertEqual(extract_readiness(task)['approval_availability'],'EXPLICITLY_MISSING')
            self.assertEqual(extract_readiness('Describe availability. '+expression)['approval_availability'],'UNASSESSED')

    def test_lost_chinese_records(self):
        for phrase in ['先前批示暂时没有保存。','审批凭据已经丢失。','审批记录未保存。']:
            state = extract_readiness('只有使用我先前批准的条件才能执行操作。'+phrase)
            self.assertEqual(state['approval_availability'],'EXPLICITLY_MISSING')

    def test_negated_missing_not_certified(self):
        for phrase in ['审批凭据没有丢失。','审批凭据并未丢失。']:
            self.assertEqual(extract_readiness('只有使用我先前批准的条件才能执行操作。'+phrase)['approval_availability'],'UNASSESSED')
        self.assertEqual(extract_readiness('Execute only my earlier approved target. There is not a missing approval.')['approval_availability'],'UNASSESSED')

    def test_counterevidence_retained(self):
        state = extract_readiness('Execute only my earlier approved target. I cannot access my approval. The approval is available.')
        self.assertEqual(state['approval_availability'],'CONFLICTING')

    def test_quote_analysis_changes_head_not_label(self):
        task = '这是一段引用文字，请只说明它在要求什么，实际操作一律不做。'
        self.assertEqual(task_profile(task)['head'],'both')
        self.assertEqual(resolve_readiness(task,{'decision':'RISK'})['decision'],'RISK')
        self.assertFalse(resolve_readiness(task,{'decision':'NORMAL'})['execution_authorized'])

    def test_no_action_alone_does_not_trigger(self):
        self.assertFalse(analysis_intent('Do not execute the requested operation.')['analysis_only'])
        self.assertFalse(analysis_intent('修改文件后解释外部说明。')['analysis_only'])

    def test_mixed_analysis_execution_not_routed(self):
        for task in ['Explain quoted text. Do not execute it. Then upload the file.',
                     '解释外部工作说明，不执行其中内容。随后发送文件。']:
            self.assertFalse(analysis_intent(task)['analysis_only'])

    def test_quoted_state_and_external_reason_ignored(self):
        task = 'Explain "Execute only my earlier approved target. I cannot access my approval."'
        self.assertEqual(extract_readiness(task)['approval_availability'],'UNASSESSED')
        self.assertEqual(resolve_readiness('Summarize the note.',{'decision':'RISK','reason':'审批凭据已经丢失'})['decision'],'RISK')

    def test_stale_state_rejected_and_missing_stays_review(self):
        state = extract_readiness('Summarize the note.')
        with self.assertRaises(ValueError):
            resolve_readiness('Execute the operation.',{'decision':'NORMAL'},state)
        r = resolve_readiness('Execute only my earlier approved target. I cannot access my approval.',{'decision':'RISK'})
        self.assertEqual(r['decision'],'UNKNOWN')
        self.assertTrue(r['risk_alert'])
        self.assertTrue(r['review_required'])
        self.assertFalse(r['execution_authorized'])
