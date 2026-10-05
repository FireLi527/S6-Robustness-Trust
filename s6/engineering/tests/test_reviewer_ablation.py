"""Numbered evidence must retain raw source identity and strict validation."""
import json
import unittest
from s6.prompt_injection.reviewer_ablation_v1 import evidence_spans,messages_for,parse_output
from s6.prompt_injection.reviewer_priority_fusion_v1 import arbitrate
from s6.prompt_injection.reviewer_refinement_v2 import messages_for as messages_v2
from s6.prompt_injection.reviewer_refinement_v3 import messages_for as messages_v3


class AblationContractTests(unittest.TestCase):
    def test_lossless_slices_include_escaped_unicode_and_tail(self):
        text = '引用 "x\\n".\n'+'甲'*650+' end'
        spans = evidence_spans(text)
        self.assertEqual(''.join(s['text'] for s in spans),text)
        for s in spans:
            self.assertEqual(text[s['start']:s['end']],s['text'])
            self.assertLessEqual(len(s['text']),320)

    def test_id_selects_source_but_not_generated_quote(self):
        v = parse_output(json.dumps({'decision':'RISK','evidence_id':1,'reason':'outside task'}),'One. Two.',True,'both')
        self.assertTrue(v['valid'])
        self.assertEqual(v['evidence'],' Two.')

    def test_invalid_boolean_id_and_missing_risk_evidence(self):
        for identifier in [True,-1,999,None,'0']:
            v = parse_output(json.dumps({'decision':'RISK','evidence_id':identifier,'reason':'reason'}),'data',True,'evidence_only')
            self.assertFalse(v['valid'])

    def test_no_eos_and_whitespace_span_rejected(self):
        text = json.dumps({'decision':'RISK','evidence_id':0,'reason':'reason'})
        self.assertFalse(parse_output(text,'data',False,'both')['valid'])
        self.assertFalse(parse_output(text,'  ',True,'both')['valid'])

    def test_labels_never_enter_model_payload(self):
        row = {'task':'Read the page','content':'A page','expected':'RISK'}
        a = messages_for(row,'both')
        b = messages_for({**row,'expected':'NORMAL'},'both')
        self.assertEqual(a,b)

    def test_text_arm_keeps_exact_substring_requirement(self):
        text = json.dumps({'decision':'RISK','evidence':'invented','reason':'reason'})
        self.assertFalse(parse_output(text,'data',True,'prompt_only')['valid'])

    def test_arbitration_does_not_erase_missing_authorization(self):
        self.assertEqual(arbitrate('RISK','UNKNOWN'),'UNKNOWN')
        self.assertEqual(arbitrate('RISK','NORMAL'),'NORMAL')
        self.assertEqual(arbitrate('RISK','INVALID'),'RISK')
        self.assertEqual(arbitrate('NORMAL','INVALID'),'UNKNOWN')

    def test_refinements_keep_source_payload_and_label_blindness(self):
        row = {'task':'Read a document','content':'A document.','expected':'RISK'}
        for builder in (messages_v2,messages_v3):
            a = builder(row,'both')
            b = builder({**row,'expected':'NORMAL'},'both')
            self.assertEqual(a,b)
            self.assertEqual(a[1],messages_for(row,'both')[1])
