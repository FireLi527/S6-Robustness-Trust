"""Train a fixed supervised baseline on all eligible BIPIA train sources."""
import copy
import csv
import json
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score

from supervised_data import ROOT, TASKS, SEED, source_records, split_sources, catalogs, variants, model_text
from detector import detect_prompt_injection, detector_metadata

OUT = ROOT / "results/bipia/supervised"
DATA = ROOT / "data/bipia/supervised"

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def metrics(labels, detected, scores=None):
    y=np.asarray(labels); p=np.asarray(detected, dtype=bool)
    tp=int(((y==1)&p).sum()); fn=int(((y==1)&~p).sum())
    fp=int(((y==0)&p).sum()); tn=int(((y==0)&~p).sum())
    result=dict(tp=tp,fn=fn,fp=fp,tn=tn,attack_detection_rate=tp/(tp+fn) if tp+fn else None,
                false_positive_rate=fp/(fp+tn) if fp+tn else None)
    result["balanced_accuracy"]=(tp/(tp+fn)+tn/(fp+tn))/2 if tp+fn and fp+tn else None
    if scores is not None and len(set(labels))==2:
        result["roc_auc"]=float(roc_auc_score(y,scores))
    return result

def choose_threshold(y, scores, tasks):
    # A single threshold, constrained by validation clean FPR <=5% IN EACH task.
    # Maximise macro-task recall; tie-break towards the higher threshold.
    best=None
    for threshold in np.r_[np.linspace(0,1,201), np.nextafter(1.,2.)]:
        per=[]
        for task in TASKS:
            take=np.asarray(tasks)==task
            per.append(metrics(np.asarray(y)[take], np.asarray(scores)[take]>=threshold))
        if any(m["false_positive_rate"]>.05 for m in per):
            continue
        objective=np.mean([m["attack_detection_rate"] for m in per])
        if best is None or (objective,threshold)>(best[0],best[1]):
            best=(objective,float(threshold),per)
    if best is None:
        raise ValueError("No feasible validation threshold")
    return best

def source_batch(source, catalog, split):
    kind="code" if source["task"]=="code" else "text"
    return list(variants(source,catalog[kind,"test" if split=="test" else "train"]))

def score_sources(model, vectorizer, sources, catalog, split):
    labels=[]; scores=[]; tasks=[]
    for source in sources:
        batch=source_batch(source,catalog,split)
        x=vectorizer.transform(model_text(r["question"],r["context"]) for r in batch)
        scores.extend(model.predict_proba(x)[:,1].tolist())
        labels.extend(r["label"] for r in batch)
        tasks.extend([source["task"]]*len(batch))
    return labels,scores,tasks

def main():
    start=time.time()
    OUT.mkdir(parents=True,exist_ok=True); DATA.mkdir(parents=True,exist_ok=True)
    if (OUT/"model.joblib").exists():
        raise RuntimeError("Frozen trained model already exists; do not overwrite or retune after viewing test results")
    rows, hashes=source_records(); splits=split_sources(rows)
    catalog, attack_hashes, excluded=catalogs(); hashes.update(attack_hashes)
    import hashlib
    code_hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                 for name in ("supervised_data.py","train_supervised.py","detector.py","semantic_detector.py")}
    counts={s:{t:sum(r["task"]==t for r in rs) for t in TASKS} for s,rs in splits.items()}
    protocol=dict(seed=SEED,epochs=3,features="word unigram/bigram hashing, 2**18 dimensions, L2, no fitted vocabulary",
                  classifier="SGD logistic loss, alpha=1e-5, constant eta0=0.01, averaged parameters",
                  input="question plus untrusted context only; full text, no truncation",
                  class_balance="Each source's clean feature row repeated to equal its attack rows during training only",
                  validation="20% source-content groups per task; test-overlap train sources excluded",
                  selection="Best validation macro-task recall under each-task clean FPR<=5%; thresholds grid 0..1 step .005 plus allow-all",
                  source_counts=counts,excluded_attack_categories=excluded,input_hashes=hashes,code_hashes=code_hashes,
                  sklearn_version=sklearn.__version__,limitations=["Only training attack templates used; validation holds out content, not templates.",
                  "Previously inspected test benchmark, not a pristine blind test.","Exact whitespace-normalised content grouping does not remove near duplicates.",
                  "Generated variants are correlated; sample counts are not independent documents."])
    frozen=DATA/"protocol.json"
    if frozen.exists() and json.loads(frozen.read_text(encoding="utf-8"))!=protocol:
        raise ValueError("Protocol already frozen and differs")
    write(frozen,protocol)
    write(DATA/"source_splits.json",{s:[{k:r[k] for k in ("source_id","group","task")} for r in rs] for s,rs in splits.items()})
    print("SOURCE COUNTS",json.dumps(counts),flush=True)
    vectorizer=HashingVectorizer(n_features=2**18,ngram_range=(1,2),alternate_sign=False,dtype=np.float32)
    model=SGDClassifier(loss="log_loss",alpha=1e-5,learning_rate="constant",eta0=.01,average=True,random_state=SEED)
    history=[]; best=None
    from scipy.sparse import vstack
    for epoch in range(1,4):
        rng=np.random.default_rng(SEED+epoch)
        order=rng.permutation(len(splits["train"]))
        for step,index in enumerate(order):
            source=splits["train"][index]; batch=source_batch(source,catalog,"train")
            x=vectorizer.transform(model_text(r["question"],r["context"]) for r in batch)
            n=len(batch)-1
            # Clean row is last. Balance without generating clean text duplicates.
            x=vstack([x[:n],x[-1][np.zeros(n,dtype=int)]],format="csr")
            y=np.r_[np.ones(n,dtype=int),np.zeros(n,dtype=int)]
            perm=rng.permutation(len(y))
            model.partial_fit(x[perm],y[perm],classes=np.array([0,1]))
            if step%100==0:
                print(f"epoch {epoch}/3 source {step+1}/{len(order)}",flush=True)
        y,scores,tasks=score_sources(model,vectorizer,splits["validation"],catalog,"validation")
        recall,threshold,per=choose_threshold(y,scores,tasks)
        entry=dict(epoch=epoch,validation_macro_recall=recall,threshold=threshold,by_task=dict(zip(TASKS,per)))
        history.append(entry); write(OUT/"training_history.json",history)
        print("VALIDATION",json.dumps(entry),flush=True)
        if best is None or recall>best[0]:
            best=(recall,copy.deepcopy(model),threshold,epoch)
    _,model,threshold,epoch=best
    bundle=dict(model=model,vectorizer=vectorizer,threshold=threshold,best_epoch=epoch,protocol=protocol)
    joblib.dump(bundle,OUT/"model.joblib",compress=3)
    # Selection/model frozen before scoring held-out test. No test-driven retry.
    write(OUT/"selection.json",dict(best_epoch=epoch,threshold=threshold,history=history,
          model_sha256=hashlib.sha256((OUT/"model.joblib").read_bytes()).hexdigest()))
    print("MODEL FROZEN; evaluating held-out test",flush=True)
    evaluate(bundle,splits["test"],catalog)
    print(f"COMPLETE elapsed={time.time()-start:.1f}s",flush=True)

def evaluate(bundle,sources,catalog):
    from semantic_detector import (extract_embeddings,texts_requiring_embeddings,assess_task_consistency,combine_hybrid,
                                   detector_metadata as semantic_metadata)
    # Semantic comparator is the existing Email-specific P2; do not silently extend it to code/table.
    texts=set()
    for source in sources:
        if source["task"]=="email":
            for row in source_batch(source,catalog,"test"):
                texts.update(texts_requiring_embeddings(row["question"],row["context"]))
    embeddings=extract_embeddings(list(texts),ROOT/"data/bipia/semantic_embedding_cache.npz",ROOT/"external/minilm_cache")
    records=[]
    for i,source in enumerate(sources):
        batch=source_batch(source,catalog,"test")
        x=bundle["vectorizer"].transform(model_text(r["question"],r["context"]) for r in batch)
        scores=bundle["model"].predict_proba(x)[:,1]
        for row,score in zip(batch,scores):
            rule=detect_prompt_injection(row["context"])
            entry={k:source[k] for k in ("source_id","group","task")}
            entry.update({k:row[k] for k in ("encoding","category","variant","position","label")})
            entry.update(supervised_score=float(score),supervised_detected=bool(score>=bundle["threshold"]),
                         rule_detected=rule.decision!="ALLOW",semantic_detected=None,hybrid_detected=None)
            if source["task"]=="email":
                sem=assess_task_consistency(row["question"],row["context"],embeddings)
                hybrid,_=combine_hybrid(rule.decision,rule.reasons,sem)
                entry.update(semantic_detected=sem.decision!="ALLOW",hybrid_detected=hybrid!="ALLOW")
            records.append(entry)
        if i%25==0: print(f"test source {i+1}/{len(sources)}",flush=True)
    with (OUT/"test_predictions.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0])); writer.writeheader();writer.writerows(records)
    summaries=[]
    for task in TASKS:
        for encoding in ("plain","stealth"):
            subset=[r for r in records if r["task"]==task and r["encoding"] in (encoding,"clean")]
            for system in (("supervised","rule","semantic","hybrid") if task=="email" else ("supervised","rule")):
                summaries.append(dict(task=task,encoding=encoding,system=system,
                  **metrics([r["label"] for r in subset],[r[system+"_detected"] for r in subset],
                            [r["supervised_score"] for r in subset] if system=="supervised" else None)))
    result=dict(status="COMPLETE",threshold=bundle["threshold"],best_epoch=bundle["best_epoch"],
                rule_detector=detector_metadata(),semantic_detector=semantic_metadata(),results=summaries,
                source_counts=bundle["protocol"]["source_counts"],limitations=bundle["protocol"]["limitations"])
    write(OUT/"summary.json",result)
    lines=["# 提示词注入监督分类基线", "", "三个任务：Email、Table、Code；使用完整符合协议的原始训练记录及明文/Base64攻击变体。",
           "固定哈希词特征 + 监督逻辑分类器（SGD），不是 MiniLM 微调。测试集不参与拟合或选阈值。",
           "正常样本在训练中等量重复平衡类别；表格任务原始记录较多，训练未做任务等权。",
           "", "## 原始记录使用范围", "", "| 划分 | Email | Table | Code |", "|---|---:|---:|---:|"]
    for split,counts in result["source_counts"].items():
        lines.append(f"| {split} | {counts['email']} | {counts['table']} | {counts['code']} |")
    lines += ["",f"验证选中 epoch={bundle['best_epoch']}，统一阈值={bundle['threshold']:.6f}。约束为各任务验证干净误报率不超过5%，不是对测试或实际部署的保证。",
              "", "## 同一测试输入上的对照", "", "检出包括原检测器的 REVIEW/BLOCK；监督分数超过阈值视为检出，仅建议 REVIEW，不自动阻断。",
              "", "| 任务 | 编码 | 系统 | 攻击检出率 | 干净误报率 | TP/FN | FP/TN |", "|---|---|---|---:|---:|---|---|"]
    for r in summaries:
        lines.append(f"| {r['task']} | {r['encoding']} | {r['system']} | {r['attack_detection_rate']:.2%} | {r['false_positive_rate']:.2%} | {r['tp']}/{r['fn']} | {r['fp']}/{r['tn']} |")
    lines += ["", "## 边界", "", "这是真实监督拟合结果，不是大模型微调或真实代理攻击成功率。不能用训练样本量替代独立来源数量。",
              "Email 原始 train/test 存在11组正文重叠，本协议排除了训练侧重叠记录；原有报告未覆盖这项检查。",
              "相同正文所有任务/编码/攻击位置均在同一划分；测试内部重复保留，指标按记录计算，不据此计算独立样本置信区间。",
              "训练和测试攻击类别不重叠；验证与训练共享攻击模板，因此验证性能可能高于新攻击测试。",
              "既有测试结果此前已观察，不宣称全新盲测；本次超参数预先固定，仅依据验证集选轮次和阈值。",
              "P2 仅在 Email 对比，不能把任务不相关直接等同于恶意注入。新分类器不替换已有门控策略。", ""]
    (OUT/"report_ZH.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
