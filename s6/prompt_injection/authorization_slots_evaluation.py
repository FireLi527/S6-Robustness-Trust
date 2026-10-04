"""Selective-classification metrics that never silently count REVIEW as benign."""
from __future__ import annotations

from collections import Counter


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(rows: list[dict], predictions: list[dict]) -> dict:
    """Separate extraction coverage, selective performance and referral burden."""
    if not rows or len(rows) != len(predictions):
        raise ValueError("Nonempty aligned rows required")
    if any(r["id"] != p["id"] or p["decision"] not in ("NORMAL", "RISK", "REVIEW") for r, p in zip(rows, predictions, strict=True)):
        raise ValueError("Prediction ID or decision mismatch")
    paired = list(zip(rows, predictions, strict=True))
    known = [(r, p) for r, p in paired if r["label"] in (0, 1)]
    decided = [(r, p) for r, p in known if p["decision"] != "REVIEW"]
    normal = [(r, p) for r, p in known if r["label"] == 0]
    risky = [(r, p) for r, p in known if r["label"] == 1]
    tp = sum(p["decision"] == "RISK" for _, p in risky)
    fp = sum(p["decision"] == "RISK" for _, p in normal)
    counts = Counter(p["decision"] for p in predictions)
    result = {"samples": len(rows), "known_labels": len(known), "unknown_labels": len(rows) - len(known),
              "decisions": dict(counts), "coverage_all": ratio(len(rows) - counts["REVIEW"], len(rows)),
              "coverage_known": ratio(len(decided), len(known)),
              "selective_accuracy": ratio(sum((p["decision"] == "RISK") == bool(r["label"]) for r, p in decided), len(decided)),
              "risk_auto_recall": ratio(tp, len(risky)), "normal_auto_fpr": ratio(fp, len(normal)),
              "auto_precision": ratio(tp, tp + fp), "risk_auto_normal": sum(p["decision"] == "NORMAL" for _, p in risky),
              "risk_review": sum(p["decision"] == "REVIEW" for _, p in risky),
              "normal_review": sum(p["decision"] == "REVIEW" for _, p in normal),
              "risk_count": len(risky), "normal_count": len(normal), "true_auto_risk": tp, "false_auto_risk": fp,
              "normal_review_rate": ratio(sum(p["decision"] == "REVIEW" for _, p in normal), len(normal)),
              "risk_review_rate": ratio(sum(p["decision"] == "REVIEW" for _, p in risky), len(risky))}
    result["extraction"] = extraction_metrics(paired)
    return result


def extraction_metrics(paired: list[tuple[dict, dict]]) -> dict:
    """Unknown oracle sides are excluded from slot correctness, not called wrong."""
    result = {}
    for side in ("task", "content"):
        eligible = [(r["expected_slots"][side], p[f"{side}_slots"]) for r, p in paired
                    if r.get("expected_slots") is not None and r["expected_slots"][side] is not None]
        extracted = [(truth, value) for truth, value in eligible if value is not None]
        result[side] = {"eligible": len(eligible), "extracted": len(extracted),
                        "coverage": ratio(len(extracted), len(eligible)),
                        "exact_correct": sum(truth == value for truth, value in extracted),
                        "conditional_exact_accuracy": ratio(sum(truth == value for truth, value in extracted), len(extracted)),
                        "fields": {key: {"correct": sum(truth[key] == value[key] for truth, value in extracted),
                                         "accuracy": ratio(sum(truth[key] == value[key] for truth, value in extracted), len(extracted))}
                                   for key in ("mode", "operation", "target", "excluded")}}
    eligible = [(r, p) for r, p in paired if r.get("expected_slots") is not None
                and all(r["expected_slots"][side] is not None for side in ("task", "content"))]
    extracted = [(r, p) for r, p in eligible if p["task_slots"] is not None and p["content_slots"] is not None]
    result["both"] = {"eligible": len(eligible), "extracted": len(extracted),
                       "coverage": ratio(len(extracted), len(eligible)),
                       "exact_correct": sum(all(r["expected_slots"][side] == p[f"{side}_slots"] for side in ("task", "content")) for r, p in extracted)}
    return result
