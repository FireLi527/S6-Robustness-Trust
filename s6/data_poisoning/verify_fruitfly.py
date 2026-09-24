"""Verify completed fruit-fly classification and frozen poisoning decisions."""
import csv,json
from pathlib import Path
from sklearn.metrics import accuracy_score,f1_score,confusion_matrix
from prepare_fruitfly import DATA,IMAGES,RESULTS,sha,write_json
from run_fruitfly import verify_inputs
import train_stl10_models as trainer
from semantic_detector import detector_metadata
from manifest_protocol import load_candidate_manifest,load_hidden_ground_truth,validate_candidate_truth_pair

def read_csv(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def main():
    protocol=json.loads((DATA/'protocol.json').read_text(encoding='utf-8'))
    verify_inputs(protocol)
    confirmation=json.loads((DATA/'specimen_group_confirmation.json').read_text(encoding='utf-8'))
    assert confirmation['applies_to_protocol_sha256']==sha(DATA/'protocol.json')
    s=json.loads(next((RESULTS/'model_training/clean_subset').glob('*/summary.json')).read_text())
    assert s['status']=='COMPLETE' and Path(s['checkpoint']).is_file()
    assert s['fruitfly_protocol_sha256']==sha(DATA/'protocol.json')
    assert s['trainer_sha256']==sha(Path(trainer.__file__))
    assert s['manifest_sha256']==sha(DATA/'manifests/clean_subset.csv')
    history=read_csv(Path(s['result_dir'])/'history.csv');assert len(history)==20
    audit=read_csv(DATA/'image_audit.csv')
    prediction_count={}
    for split,key in (('val','validation'),('test','test')):
        predictions=read_csv(Path(s['result_dir'])/f'{split}_predictions.csv')
        expected={r['source_relpath']:int(r['label']) for r in audit if r['status']=='valid' and r['split']==split}
        assert len(predictions)==len(expected)
        assert {r['sample_id']:int(r['true_label']) for r in predictions}==expected
        y=[int(r['true_label']) for r in predictions];p=[int(r['predicted_label']) for r in predictions]
        assert abs(accuracy_score(y,p)-s[key]['accuracy'])<1e-6
        assert abs(f1_score(y,p,average='macro')-s[key]['macro_f1'])<1e-6
        assert confusion_matrix(y,p).tolist()==s[key]['confusion_matrix']
        prediction_count[split]=len(predictions)
    aggregate=json.loads((RESULTS/'semantic_evaluation_summary.json').read_text())
    frozen=json.loads((RESULTS/'semantic_sample_results.json').read_text())
    assert aggregate['detector']==frozen['detector']==detector_metadata()
    assert aggregate['protocol_sha256']==frozen['protocol_sha256']==sha(DATA/'protocol.json')
    counts=[]
    for row in aggregate['datasets']:
        name=row['dataset'];candidate=load_candidate_manifest(DATA/'manifests'/f'{name}.csv')
        assert sha(DATA/'manifests'/f'{name}.csv')==aggregate['manifest_hashes'][name]
        truth=validate_candidate_truth_pair(candidate,load_hidden_ground_truth(DATA/'hidden_ground_truth'/f'{name}.csv'))
        decisions=frozen['datasets'][name];assert set(decisions)==set(truth)
        tp=fp=fn=tn=0
        for sid,r in truth.items():
            bad=r['poisoned'].lower()=='true';flag=decisions[sid]['decision']!='ALLOW'
            tp+=bad and flag;fp+=(not bad) and flag;fn+=bad and not flag;tn+=(not bad) and not flag
        assert abs(fp/(fp+tn)-row['clean_false_positive_rate'])<=.000051
        if tp+fn:
            assert abs(tp/(tp+fn)-row['recall'])<=.000051
            assert abs(tp/(tp+fp)-row['precision'])<=.000051
        counts.append(dict(dataset=name,detected_poison=tp,missed_poison=fn,flagged_clean=fp,allowed_clean=tn))
    write_json(RESULTS/'verification.json',dict(status='VERIFIED',protocol_sha256=sha(DATA/'protocol.json'),
       checkpoint_sha256=sha(Path(s['checkpoint'])),prediction_count=prediction_count,
       specimen_group_confirmed=True,detector_counts=counts))
    report=RESULTS/'report_ZH.md';text=report.read_text(encoding='utf-8')
    note='> 补充确认：用户已向同学确认文件名前9位为同一标本编号，当前分类训练/验证/测试集按标本隔离。下文未确认表述为运行时历史记录，由本条更新；冻结协议未改动。检测器内部交叉验证仍按图片分折。\n\n'
    if '> 补充确认：' not in text:text=text.replace('\n\n','\n\n'+note,1)
    text+='\n核验通过：全部9244张图片字节、分组隔离、模型检查点、1392条验证与1321条测试预测、四组投毒检测计数。详见 verification.json。\n' if '核验通过：' not in text else ''
    report.write_text(text,encoding='utf-8')
    print(json.dumps(dict(classification=s['test'],detector_counts=counts,status='VERIFIED'),ensure_ascii=False))

if __name__=='__main__':main()
