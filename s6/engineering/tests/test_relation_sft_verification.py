import copy
import json
import unittest
from pathlib import Path
from s6.engineering.artifacts import read_json
from s6.prompt_injection.relation_sft_io import messages, score, FEWSHOT_IDS
from s6.prompt_injection.verify_relation_sft_v1 import verify_predictions


class VerificationContracts(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3]
        self.rows = read_json(root / 'data/bipia/relation_sft_v1/samples.json')
        lookup = {r['id']: r for r in self.rows}
        examples = [lookup[i] for i in FEWSHOT_IDS]
        self.predictions = []
        for row in self.rows:
            if row['split'] == 'train':
                continue
            for side in ('task','content'):
                for arm in ('base_zero','base_fewshot','adapter_zero'):
                    text = json.dumps(row['targets'][side], ensure_ascii=False)
                    self.predictions.append({'id':row['id'],'side':side,'split':row['split'],'arm':arm,
                        'input_messages':messages(row,side,examples if arm == 'base_fewshot' else None),
                        'input_tokens':1,'output_tokens':1,'input_ids':[1],'generated_token_ids':[2],
                        'text':text,'finished':True,'score':score(text,True,row['inputs'][side],row['targets'][side])})
        self.summary = {split:{arm:{'side_samples':12,'valid':12,'mode_correct':12,'actions_exact':12,'fields_exact':12,'unfinished':0}
                        for arm in ('base_zero','base_fewshot','adapter_zero')} for split in ('validation','test')}

    def test_full_replay(self):
        self.assertEqual(verify_predictions(self.rows,self.predictions,self.summary)['calls_replayed'],72)

    def test_duplicate_call_rejected(self):
        with self.assertRaises(ValueError):
            verify_predictions(self.rows,self.predictions + [self.predictions[0]],self.summary)

    def test_oracle_input_rejected(self):
        changed = copy.deepcopy(self.predictions)
        changed[0]['input_messages'][-1]['content'] = '{"label":"NORMAL"}'
        with self.assertRaises(ValueError):
            verify_predictions(self.rows,changed,self.summary)


if __name__ == '__main__':
    unittest.main()
