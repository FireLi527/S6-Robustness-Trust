"""Exploratory closed-set intent comparison on the 18 authored tool demos.

Prediction sees content and fixed intent prototypes only. Reference tool categories
and attack labels are joined AFTER prediction. They are demo proxies, not independently
annotated user intentions. This module never changes the production P1/P2/P3 flow.
"""
import hashlib
import json
import threading
from collections import Counter
from pathlib import Path
import numpy as np
from confused_deputy_scenarios import SCENARIOS
from task_intent import PRESETS
from detector import detect_prompt_injection
from semantic_detector import (embed_texts, text_sha256, texts_requiring_embeddings,
    assess_task_consistency, combine_hybrid, detector_metadata)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "results/bipia/intent_comparison/report.json"
MODEL_CACHE = ROOT / "external/minilm_cache"
LOCK = threading.Lock()
# Fixed before running the comparison; no fitting or threshold tuning on these demos.
LABELS = {
    "read_email": {"zh": "邮件阅读", "en": "Email reading"},
    "search_documents": {"zh": "文档检索", "en": "Document search"},
    "create_calendar_event": {"zh": "日程安排", "en": "Scheduling"},
    "send_email": {"zh": "邮件发送", "en": "Email sending"},
    "delete_records": {"zh": "记录清理", "en": "Record cleanup"},
    "access_secret": {"zh": "访问凭据", "en": "Credential access"},
}
PROTOTYPES = {
    "read_email": "Read an email message and answer a question about its contents.",
    "search_documents": "Find and retrieve a document or template from a shared documents folder.",
    "create_calendar_event": "Schedule a meeting and create a calendar event or invitation.",
    "send_email": "Send or forward an email message to a recipient.",
    "delete_records": "Delete or remove old records, logs, backups, or duplicate archive entries.",
    "access_secret": "Access or retrieve passwords, keys, credentials, or information in a secrets vault.",
}

def signature():
    data = {"prototypes": PROTOTYPES, "tasks": PRESETS, "p2": detector_metadata(),
            "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scenarios": [(s.scenario_id, s.content, s.tool_call.tool_name, s.triggered_by_untrusted_content) for s in SCENARIOS]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def unit(vector):
    vector = np.asarray(vector, dtype=float)
    if not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
        raise ValueError("Invalid intent embedding")
    return vector / np.linalg.norm(vector)

def predict_intent(text, embeddings):
    # No scenario object, tool name, description, task context, or ground truth input.
    vector = unit(embeddings[text_sha256(text)])
    ranked = sorted(((name, float(vector @ unit(embeddings[text_sha256(prototype)])))
                     for name, prototype in PROTOTYPES.items()), key=lambda x: x[1], reverse=True)
    return {"label": ranked[0][0], "similarity": ranked[0][1],
            "margin": ranked[0][1] - ranked[1][1],
            "scores": dict(ranked), "question": PRESETS[ranked[0][0]]}

def metrics(labels, decisions):
    hits = [d in ("REVIEW", "BLOCK") for d in decisions]
    tp = sum(y and p for y, p in zip(labels, hits)); fp = sum(not y and p for y, p in zip(labels, hits))
    fn = sum(y and not p for y, p in zip(labels, hits)); tn = sum(not y and not p for y, p in zip(labels, hits))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0}

def evaluate(embedding_fn=embed_texts):
    texts = list(PROTOTYPES.values()) + [s.content for s in SCENARIOS]
    # All six task profiles are available to every prediction, not just the correct one.
    for s in SCENARIOS:
        for task in PRESETS.values():
            texts.extend(texts_requiring_embeddings(task, s.content))
    embeddings = embedding_fn(list(dict.fromkeys(texts)), MODEL_CACHE)
    predictions = [predict_intent(s.content, embeddings) for s in SCENARIOS]
    rows = []
    for s, predicted in zip(SCENARIOS, predictions):
        reference = s.tool_call.tool_name
        rule = detect_prompt_injection(s.content)
        known = assess_task_consistency(PRESETS[reference], s.content, embeddings)
        inferred = assess_task_consistency(predicted["question"], s.content, embeddings)
        rows.append({"scenario_id": s.scenario_id, "content": s.content,
            "reference": reference, "predicted": predicted["label"], "match": reference == predicted["label"],
            "similarity": predicted["similarity"], "margin": predicted["margin"],
            "reference_task": PRESETS[reference], "inferred_task": predicted["question"],
            "is_injection": s.triggered_by_untrusted_content,
            "rule": rule.decision, "preset_p2": known.decision, "auto_p2": inferred.decision,
            "preset_hybrid": combine_hybrid(rule.decision, rule.reasons, known)[0],
            "auto_hybrid": combine_hybrid(rule.decision, rule.reasons, inferred)[0]})
    references = Counter(row["reference"] for row in rows)
    per_class = {name: {"count": references[name], "correct": sum(r["match"] for r in rows if r["reference"] == name)} for name in LABELS}
    labels = [r["is_injection"] for r in rows]
    return {"signature": signature(), "status": "COMPLETE", "model": "all-MiniLM-L6-v2 (frozen)",
            "method": "cosine nearest prototype; top-1 over six fixed task categories; no training",
            "scope": "18 authored P3 demos; reference is configured tool category, not independently annotated intent",
            "similarity_is_probability": False, "affects_live_policy": False,
            "count": len(rows), "correct": sum(r["match"] for r in rows),
            "agreement": sum(r["match"] for r in rows) / len(rows),
            "macro_recall": sum(v["correct"] / v["count"] for v in per_class.values() if v["count"]) / sum(v["count"] > 0 for v in per_class.values()),
            "majority_baseline": max(references.values()) / len(rows), "per_class": per_class,
            "attack_count": sum(labels), "clean_count": len(labels) - sum(labels),
            "detection": {key: metrics(labels, [r[key] for r in rows]) for key in ("rule", "preset_p2", "auto_p2", "preset_hybrid", "auto_hybrid")},
            "labels": LABELS, "rows": rows}

def load_report():
    if not OUTPUT.is_file():
        return {"status": "NOT_RUN"}
    report = json.loads(OUTPUT.read_text(encoding="utf-8"))
    return report if report.get("signature") == signature() else {"status": "STALE"}

def run_comparison():
    with LOCK:
        existing = load_report()
        if existing["status"] == "COMPLETE":
            return existing
        report = evaluate()
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(OUTPUT)
        return report

if __name__ == "__main__":
    result = run_comparison()
    print(json.dumps({k: result[k] for k in ("count", "correct", "agreement", "majority_baseline", "detection")}, indent=2))
