"""Exploratory family-held-out comparison on 36 previously reviewed examples.

Never modifies old training splits or models. Not a new independent test set.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, make_pipeline
from semantic_detector import extract_embeddings, text_sha256, EMBEDDING_MODEL

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/repo_file_v2"
OUT = ROOT / "results/bipia/joint_context_v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(labels, predictions):
    y, p = np.asarray(labels), np.asarray(predictions)
    tp, fp = int(((y == 1) & (p == 1)).sum()), int(((y == 0) & (p == 1)).sum())
    positives, negatives = int((y == 1).sum()), int((y == 0).sum())
    return {"samples":len(y), "attacks":positives, "benign":negatives, "tp":tp, "fp":fp,
            "recall":tp / positives, "fpr":fp / negatives,
            "precision":tp / (tp + fp) if tp + fp else None, "accuracy":float((y == p).mean())}


def load_rows():
    review = json.loads((DATA / "human_review_completion.json").read_text(encoding="utf-8"))
    rows = []
    for batch in ("batch1", "batch2"):
        path = DATA / f"candidate_{batch}.json"
        assert digest(path) == review[batch]["candidate_sha256"]
        samples = json.loads(path.read_text(encoding="utf-8"))["samples"]
        benign, attacks = set(review[batch]["benign"]), set(review[batch]["injection"])
        assert not benign & attacks
        assert benign | attacks == {s["review_number"] for s in samples}
        for sample in samples:
            rows.append({"id":sample["sample_id"], "task":sample["user_task"],
                         "content":sample["content"], "family":sample["split_group"],
                         "label":int(sample["review_number"] in attacks)})
    assert len(rows) == 36 and sum(r["label"] for r in rows) == 18
    return rows


def main():
    rows = load_rows()
    groups = sorted({r["family"] for r in rows})
    assert len(groups) == 6
    protocol = {"version":"joint-context-v1", "status":"exploratory_development_cv",
                "data":"36 AI-authored, single-user reviewed examples; previously used for development",
                "split":"leave-one-family-out; six folds; related examples from both batches stay together",
                "threshold":0.5, "threshold_selection":"fixed in advance; no calibration on held-out folds",
                "classifier":{"type":"LogisticRegression", "C":1.0, "class_weight":"balanced", "solver":"liblinear", "random_state":2026},
                "embedding":{"model":EMBEDDING_MODEL, "frozen":True, "max_length":128},
                "joint_features":"task, content, abs(task-content), task*content, cosine",
                "arms":["tfidf_content", "minilm_task_only", "minilm_content", "minilm_joint"],
                "families":groups, "source_hashes":{p.name:digest(p) for p in (DATA / "candidate_batch1.json", DATA / "candidate_batch2.json", DATA / "human_review_completion.json")},
                "code_sha256":digest(Path(__file__)), "new_external_test_used":False, "deployment":False}
    OUT.mkdir(parents=True, exist_ok=True)
    protocol_path = OUT / "protocol.json"
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text(encoding="utf-8")) == protocol, "Protocol changed; use a new version"
    else:
        protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    embeddings = extract_embeddings([r[k] for r in rows for k in ("task", "content")],
                                    OUT / "embeddings.npz", ROOT / "external/minilm_cache", batch_size=16)
    task = np.stack([embeddings[text_sha256(r["task"])] for r in rows])
    content = np.stack([embeddings[text_sha256(r["content"])] for r in rows])
    features = {"minilm_task_only":task, "minilm_content":content,
                "minilm_joint":np.concatenate([task, content, abs(task-content), task*content,
                                                np.sum(task*content,axis=1,keepdims=True)], axis=1)}
    y = np.array([r["label"] for r in rows])
    scores = {arm:np.zeros(len(rows)) for arm in protocol["arms"]}
    for family in groups:
        test = np.array([r["family"] == family for r in rows]); train = ~test
        assert set(y[train]) == {0,1} and set(y[test]) == {0,1}
        for arm in protocol["arms"]:
            model = LogisticRegression(**{k:v for k,v in protocol["classifier"].items() if k != "type"}, max_iter=2000)
            if arm == "tfidf_content":
                model = make_pipeline(FeatureUnion([
                    ("word", TfidfVectorizer(ngram_range=(1,2), min_df=2)),
                    ("char", TfidfVectorizer(analyzer="char", ngram_range=(3,5), min_df=2))]), model)
                texts = np.array([r["content"] for r in rows])
                model.fit(texts[train].tolist(), y[train])
                score = model.predict_proba(texts[test].tolist())[:,1]
            else:
                model.fit(features[arm][train], y[train]); score = model.predict_proba(features[arm][test])[:,1]
            scores[arm][test] = score
    summary = {arm:metrics(y, score >= .5) for arm,score in scores.items()}
    per_family = {family:{arm:metrics(y[mask], score[mask] >= .5) for arm,score in scores.items()}
                  for family in groups for mask in [np.array([r["family"] == family for r in rows])]}
    predictions = [{**row, "scores":{arm:float(score[i]) for arm,score in scores.items()}} for i,row in enumerate(rows)]
    for name, value in (("summary.json", {"overall":summary, "per_family":per_family}), ("predictions.json",predictions)):
        (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 用户任务＋正文联合检测：探索性对照", "",
             "36条已用于开发的人工审核合成样本，18攻击、18正常。按6个模板家族留一交叉验证；不是新增独立测试集。原训练划分和已有模型不变。",
             "", "冻结MiniLM，只训练逻辑回归。阈值预设0.5，未使用评估折调参；TF-IDF在每折训练部分重新拟合。没有使用无任务字段的公开数据伪造任务。", "",
             "|方法|攻击检出|正常误报|准确率|精确率|", "|---|---:|---:|---:|---:|"]
    for arm, m in summary.items():
        precision = f'{m["precision"]:.2%}' if m["precision"] is not None else "未定义"
        lines.append(f'|{arm}|{m["tp"]}/18 ({m["recall"]:.2%})|{m["fp"]}/18 ({m["fpr"]:.2%})|{m["accuracy"]:.2%}|{precision}|')
    lines += ["", "## 解释边界", "",
              "仅18个正常样本，1个误报就对应5.56%；无法可靠验证5%误报率目标。每折约30条训练样本，联合特征1537维，结果仅用于研究方向筛选，不能宣称统计显著或真实代理防御成功率。",
              "任务单独输入是捷径对照；同一任务可能同时对应正常和攻击文本，仅识别任务类别不足以判断注入。",
              "本实验没有新增独立任务配对语料，也未完成可靠的分域阈值校准。后续需要独立来源的真实任务＋正文标签，分来源验证阈值，再使用未触碰测试集评估。",
              "检测模型不参与任务范围确认，不自动授权工具；本次结果不替换前端现用模型。"]
    (OUT / "report_ZH.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
