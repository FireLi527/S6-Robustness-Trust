"""Native task/tool-result pairs: frozen grouped split, then fit, then one test run.

Upstream data are untrusted strings, never imported as code or executed.
Source-provided benchmark tasks are not real-world user-collection records.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

from detector import detect_prompt_injection
from experiment_joint_context_v1 import load_rows as reviewed_rows
from semantic_detector import extract_embeddings, text_sha256, _load_model
from train_repo_file_v1 import make_pipeline, frozen_rows, confusion

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "external/AgentInjectionBench/data/agent_injection_bench.jsonl"
DATA = ROOT / "data/bipia/native_pairs_v1"
OUT = ROOT / "results/bipia/native_pairs_v1"
ARMS = ("tfidf_content", "minilm_task_only", "minilm_content", "minilm_joint")
REVISION = "5adb09800170683793b4e4d015e42e2002fa5adf"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize(text):
    return " ".join(text.casefold().split())


def threshold_for(labels, scores):
    candidates = [float(np.nextafter(max(scores), np.inf)), *sorted(set(map(float, scores))), 0.0]
    valid = [(confusion(labels, scores >= t), t) for t in candidates]
    valid = [(m,t) for m,t in valid if m["fpr"] <= .05]
    metrics, threshold = max(valid, key=lambda x:(x[0]["recall"], -x[0]["fpr"], x[1]))
    return threshold, metrics


def prepare():
    if DATA.exists():
        raise FileExistsError("Dataset version exists; do not overwrite")
    upstream = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    rows, exclusions = [], []
    for row in upstream:
        reason = None
        if row["injection_surface"] == "file_content": reason = "previously_evaluated_file_content"
        elif row["complexity"] != "single_turn": reason = "multi_turn_or_chained_not_supported"
        elif [t["role"] for t in row["conversation"]] != ["user", "tool_result", "assistant"]: reason = "unsupported_conversation_shape"
        elif row["ground_truth"] not in {"safe", "unsafe"}: reason = "unknown_label"
        if reason:
            exclusions.append({"id":row["id"], "reason":reason}); continue
        task, content = [t["content"] for t in row["conversation"][:2]]
        if not all(isinstance(x,str) and x.strip() for x in (task,content)):
            raise ValueError("Empty or non-text native pair")
        rows.append({"id":row["id"], "task":task, "content":content,
                     "label":int(row["ground_truth"] == "unsafe"), "surface":row["injection_surface"],
                     "source_task":"conversation[0].content", "source_content":"conversation[1].content",
                     "label_basis":"upstream ground_truth; no new human review", "source_revision":REVISION})
    # Exclude lexical near-duplicates of old source data and reviewed development samples.
    _, old = frozen_rows()
    references = [r["text"] for r in old] + [r["content"] for r in reviewed_rows()]
    references += [r["conversation"][1]["content"] for r in upstream if r["injection_surface"] == "file_content"]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3,5), min_df=2, max_features=100000)
    matrix = vectorizer.fit_transform([normalize(r["content"]) for r in rows] + [normalize(x) for x in references])
    maximum = (matrix[:len(rows)] @ matrix[len(rows):].T).max(axis=1).toarray().ravel()
    retained = []
    for row, similarity in zip(rows, maximum):
        if similarity >= .88:
            exclusions.append({"id":row["id"], "reason":"near_duplicate_of_previously_used_text", "similarity":float(similarity)})
        else: retained.append(row)
    rows = retained
    # Connected components: equal normalized tasks or >=.88 content similarity cannot cross splits.
    matrix = vectorizer.transform([normalize(r["content"]) for r in rows])
    similar = (matrix @ matrix.T).toarray()
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(rows)):
        for j in range(i):
            if normalize(rows[i]["task"]) == normalize(rows[j]["task"]) or similar[i,j] >= .88:
                parent[find(i)] = find(j)
    groups = np.array([find(i) for i in range(len(rows))])
    y = np.array([r["label"] for r in rows])
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=2026).split(np.zeros(len(rows)), y, groups))
    assignments = np.array(["train"] * len(rows), dtype=object)
    assignments[folds[0][1]] = "test"; assignments[folds[1][1]] = "validation"
    # One example was read during schema inspection; keep its entire group in training.
    inspected = {groups[i] for i,r in enumerate(rows) if r["id"] == "AIB-00001"}
    for i,row in enumerate(rows):
        if groups[i] in inspected: assignments[i] = "train"
        row.update(split=str(assignments[i]), group_id=f"aib-native-{groups[i]}")
    counts = {s:dict(Counter("attack" if r["label"] else "benign" for r in rows if r["split"] == s)) for s in ("train","validation","test")}
    assert all(counts[s].get("benign",0) >= 5 and counts[s].get("attack",0) >= 5 for s in counts), counts
    for s in counts:
        assert not {r["group_id"] for r in rows if r["split"] == s} & {r["group_id"] for r in rows if r["split"] != s}
    DATA.mkdir(parents=True)
    save(DATA / "samples.json", rows)
    save(DATA / "exclusions.json", exclusions)
    protocol = {"status":"FROZEN_BEFORE_FIT", "source_url":"https://github.com/ppradyoth/AgentInjectionBench",
                "source_revision":REVISION, "source_sha256":sha(SOURCE), "license":"Apache-2.0",
                "data_kind":"upstream benchmark-native task/tool-result pairs, not real-user collected data",
                "label_basis":"upstream safe/unsafe; assistant responses, attack taxonomy, severity, notes excluded from model inputs",
                "source_count":len(upstream), "retained":len(rows), "excluded":len(exclusions), "counts":counts,
                "samples_sha256":sha(DATA / "samples.json"), "code_sha256":sha(Path(__file__)),
                "model_helpers_sha256":{name:sha(Path(__file__).with_name(name)) for name in ("train_repo_file_v1.py", "semantic_detector.py", "experiment_joint_context_v1.py")},
                "reference_scope":"all original repo-file source, 36 reviewed examples, 10 previously evaluated AIB file-content cases",
                "near_duplicate_cosine":.88, "split":"5 stratified group folds; fold0 test, fold1 validation, others train; inspected AIB-00001 group forced train",
                "seed":2026, "arms":ARMS, "classifier":"balanced logistic regression C=1 liblinear; no hyperparameter search",
                "encoder":"frozen all-MiniLM-L6-v2; mean pool, normalized, max_length=128",
                "joint_features":"task, content, abs(task-content), task*content, cosine",
                "threshold":"maximize validation recall under empirical FPR<=5%; tie by lower FPR then higher threshold; reject-all permitted",
                "report_fixed_threshold":.5, "test_policy":"test read for grouping only; no embeddings or scores before model+threshold freeze; score once",
                "cross_source_diagnostic":"36 earlier-reviewed, previously seen development cases; NOT a fresh independent test",
                "limitations":["Same-source held-out test, not independent-source test.", "Lexical grouping cannot rule out hidden template-family overlap.", "Single seed and small benign validation/test counts; 5% constraint is not a population guarantee.", "No permission policy or live frontend model changes."]}
    save(DATA / "protocol.json", protocol)
    (DATA / "LICENSE-Apache-2.0.txt").write_bytes((SOURCE.parents[1] / "LICENSE").read_bytes())
    print(json.dumps({"counts":counts,"exclusions":dict(Counter(r["reason"] for r in exclusions))},ensure_ascii=False,indent=2))


def load():
    protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["code_sha256"] == sha(Path(__file__))
    assert protocol["samples_sha256"] == sha(DATA / "samples.json")
    assert protocol["source_sha256"] == sha(SOURCE)
    for name,digest in protocol["model_helpers_sha256"].items():
        assert sha(Path(__file__).with_name(name)) == digest
    return protocol, json.loads((DATA / "samples.json").read_text(encoding="utf-8"))


def features(rows):
    texts = [r[k] for r in rows for k in ("task","content")]
    cache = extract_embeddings(texts, OUT / "embeddings.npz", ROOT / "external/minilm_cache", batch_size=16)
    task = np.stack([cache[text_sha256(r["task"])] for r in rows])
    content = np.stack([cache[text_sha256(r["content"])] for r in rows])
    values = {"minilm_task_only":task, "minilm_content":content,
              "minilm_joint":np.concatenate([task, content, abs(task-content), task*content, np.sum(task*content,axis=1,keepdims=True)],axis=1),
              "tfidf_content":[r["content"] for r in rows]}
    tokenizer,_ = _load_model(str(ROOT / "external/minilm_cache"))
    truncation = {k:sum(len(tokenizer(r[k],truncation=False)["input_ids"]) > 128 for r in rows) for k in ("task","content")}
    return values, truncation


def fit():
    protocol, rows = load()
    if (OUT / "selection.json").exists(): raise FileExistsError("Selection already frozen")
    OUT.mkdir(parents=True,exist_ok=True)
    train, val = [[r for r in rows if r["split"] == s] for s in ("train","validation")]
    xtrain,ttrain = features(train); xval,tval = features(val)
    ytrain, yval = np.array([r["label"] for r in train]), np.array([r["label"] for r in val])
    models, selection = {}, {}
    for arm in ARMS:
        model = make_pipeline() if arm == "tfidf_content" else LogisticRegression(C=1,class_weight="balanced",solver="liblinear",random_state=2026,max_iter=2000)
        model.fit(xtrain[arm],ytrain)
        scores = model.predict_proba(xval[arm])[:,1]
        threshold, result = threshold_for(yval,scores)
        models[arm] = model
        selection[arm] = {"threshold":threshold,"validation":result,"fixed_05_validation":confusion(yval,scores >= .5)}
    joblib.dump(models, OUT / "models.joblib")
    save(OUT / "selection.json", {"protocol_sha256":sha(DATA / "protocol.json"),"models_sha256":sha(OUT / "models.joblib"),
                                  "arms":selection, "truncated_text_counts":{"train":ttrain,"validation":tval}})
    print(json.dumps(selection,indent=2))


def evaluate():
    protocol, rows = load()
    if (OUT / "test_started.json").exists(): raise FileExistsError("Test already started; no repeated selection")
    selection = json.loads((OUT / "selection.json").read_text(encoding="utf-8"))
    assert selection["protocol_sha256"] == sha(DATA / "protocol.json")
    assert selection["models_sha256"] == sha(OUT / "models.joblib")
    save(OUT / "test_started.json", {"selection_sha256":sha(OUT / "selection.json")})
    models = joblib.load(OUT / "models.joblib")
    datasets = {"aib_held_out_test":[r for r in rows if r["split"] == "test"],
                "reviewed36_seen_cross_source_diagnostic":reviewed_rows()}
    summary, predictions = {}, {}
    for name, subset in datasets.items():
        x, truncation = features(subset); y = np.array([r["label"] for r in subset])
        p1 = np.array([detect_prompt_injection(r["content"]).decision != "ALLOW" for r in subset])
        summary[name] = {"samples":len(subset), "attacks":int(y.sum()), "benign":int((y==0).sum()),
                         "truncated_text_counts":truncation,"p1":confusion(y,p1),"arms":{}}
        predictions[name] = [{"id":r["id"],"label":r["label"],"scores":{},"p1_flag":bool(p)} for r,p in zip(subset,p1)]
        for arm,model in models.items():
            scores = model.predict_proba(x[arm])[:,1]
            threshold = selection["arms"][arm]["threshold"]
            summary[name]["arms"][arm] = {"threshold":threshold,"calibrated":confusion(y,scores >= threshold),"fixed_05":confusion(y,scores >= .5)}
            for row,score in zip(predictions[name],scores): row["scores"][arm] = float(score)
    save(OUT / "summary.json", summary); save(OUT / "predictions.json", predictions)
    lines = ["# 原生任务配对补充实验", "", f'纳入AgentInjectionBench {protocol["retained"]}条单轮原生任务＋工具返回配对，来源版本 `{REVISION}`，Apache-2.0。并非真实用户采集数据。',
             "", "按任务和正文近重复分组划分；此前用过的10条文件场景及多轮/链式场景排除。助手答复和标签元信息不进入模型输入。", "",
             "模型与阈值先在训练/验证集冻结，然后一次性评分留出测试。旧模型、旧数据和前端默认模型均未改变。", "",
             "划分计数：`"+json.dumps(protocol["counts"],ensure_ascii=False)+"`", "",
             "## 同来源留出测试（不是独立来源测试）", "", "|方法|准确率|攻击召回率|正常误报率|TP/FP|", "|---|---:|---:|---:|---:|"]
    def table_row(arm,m):
        return f'|{arm}|{m["accuracy"]:.2%}|{m["recall"]:.2%}|{m["fpr"]:.2%}|{m["tp"]}/{m["fp"]}|'
    test = summary["aib_held_out_test"]
    lines.append(table_row("P1（REVIEW或BLOCK算检出）",test["p1"]))
    lines += [table_row(arm,r["calibrated"]) for arm,r in test["arms"].items()]
    lines += ["", f'测试集：{test["attacks"]}攻击、{test["benign"]}正常。验证误报率≤5%只是小样本经验约束，不保证测试或实际部署误报率。',
              "", "## 跨来源开发诊断（36条已见样本）", "", "|方法|准确率|攻击召回率|正常误报率|TP/FP|", "|---|---:|---:|---:|---:|"]
    diagnostic = summary["reviewed36_seen_cross_source_diagnostic"]
    lines.append(table_row("P1",diagnostic["p1"]))
    lines += [table_row(arm,r["calibrated"]) for arm,r in diagnostic["arms"].items()]
    lines += ["", "这36条未用于本轮训练，但此前已用于项目开发，不能称为全新独立测试。固定0.5阈值对照、逐条预测和截断计数保存在JSON中，不根据测试结果重新选阈值。", "",
              "MiniLM仍冻结，最大128 token；超长正文可能丢失后文，截断数见summary.json。近重复分组不能排除隐藏模板家族重合。数据量小、单种子、上游标签未新增独立人工审核。", "",
              "结论边界：这是静态内容检测，不是LLM代理端到端攻击成功率；新模型不进入工具授权链。仍需独立来源且有足够正常样本的原生任务配对评估集。", "",
              "来源：https://github.com/ppradyoth/AgentInjectionBench （本地保留Apache-2.0许可证）"]
    (OUT / "report_ZH.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("mode",choices=("prepare","fit","evaluate"))
    {"prepare":prepare,"fit":fit,"evaluate":evaluate}[parser.parse_args().mode]()
