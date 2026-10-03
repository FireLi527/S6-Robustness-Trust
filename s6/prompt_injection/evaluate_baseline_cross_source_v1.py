"""Frozen P1 rule / P2 semantic / hybrid on InjecAgent and NotInject: no retuning, CPU only.

P2 needs the user task; NotInject has none, so P2 is reported as not applicable there and
the hybrid equals P1. Any REVIEW or BLOCK counts as a detection (or a false alarm).
"""
from collections import Counter
from pathlib import Path
import sys
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/cross_source_v1"
MODEL_CACHE = ROOT / "external/minilm_cache"
OUT = ROOT / "results/bipia/baseline_cross_source_v1"
SOURCES = ("injecagent", "notinject")


def load_detectors():
    """Legacy modules use sibling imports, so their directory is put on the path explicitly."""
    folder = str(Path(__file__).resolve().parent)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import detector
    import semantic_detector
    return detector, semantic_detector


def rate(hits: int, n: int) -> dict:
    return {"hits": hits, "n": n, "rate": hits / n if n else None}


def classify(rows: list, detector, semantic, embeddings: dict) -> list:
    items = []
    for row in rows:
        rule = detector.detect_prompt_injection(row["content"])
        task = row["task"] or ""
        p2 = semantic.assess_task_consistency(task, row["content"], embeddings) if task else None
        hybrid = semantic.combine_hybrid(rule.decision, rule.reasons, p2)[0] if p2 else rule.decision
        items.append({"id": row["id"], "source": row["source"], "subset": row["id"].rsplit("-", 1)[0],
                      "label": row["label"], "rule": rule.decision,
                      "semantic": p2.decision if p2 else None, "hybrid": hybrid})
    return items


def summarize(items: list) -> dict:
    """Detection = REVIEW or BLOCK; BLOCK-only reported separately. Attack-only / benign-only sources."""
    result = {}
    for subset in sorted({i["subset"] for i in items}) + sorted({i["source"] for i in items}):
        chosen = [i for i in items if i["subset"] == subset or i["source"] == subset]
        result[subset] = {}
        for system in ("rule", "semantic", "hybrid"):
            decisions = [i[system] for i in chosen]
            if any(d is None for d in decisions):
                result[subset][system] = "not_applicable_no_user_task"
                continue
            counts = Counter(decisions)
            flagged = counts["REVIEW"] + counts["BLOCK"]
            metric = "detection_rate" if chosen[0]["label"] == 1 else "false_alarm_rate"
            result[subset][system] = {metric: rate(flagged, len(chosen)), "block": rate(counts["BLOCK"], len(chosen)),
                                      "decisions": dict(counts)}
    return result


def main() -> None:
    if read_json(DATA / "status.json")["state"] != "COMPLETE":
        raise ValueError("Cross-source data incomplete")
    require_hash(DATA / "evaluation.json", read_json(DATA / "integrity.json")["evaluation.json"])
    rows = [r for r in read_json(DATA / "evaluation.json") if r["source"] in SOURCES]
    if {r["source"]: r["label"] for r in rows} != {"injecagent": 1, "notinject": 0}:
        raise ValueError("Unexpected label layout")
    detector, semantic = load_detectors()
    texts = sorted({t for r in rows if r["task"] for t in semantic.texts_requiring_embeddings(r["task"], r["content"])})
    folder = Path(__file__).parent
    protocol = {"inputs_sha256": {"data/bipia/cross_source_v1/evaluation.json": file_sha256(DATA / "evaluation.json")},
                "code_sha256": {n: file_sha256(folder / n) for n in
                                ("evaluate_baseline_cross_source_v1.py", "detector.py", "semantic_detector.py")},
                "p1": detector.detector_metadata(), "p2": semantic.detector_metadata(),
                "rule": "Frozen P1/P2 rules, weights and thresholds; no retuning on these sources",
                "embedding_cache": "new cache inside this run; the BIPIA cache is not modified"}
    with new_run(OUT, protocol):
        embeddings = semantic.extract_embeddings(texts, OUT / "embedding_cache.npz", MODEL_CACHE)
        items = classify(rows, detector, semantic, embeddings)
        write_json(OUT / "decisions.json", items)
        write_json(OUT / "summary.json", summarize(items))
    print(f"Baseline cross-source evaluation COMPLETE: {len(items)} records", flush=True)


if __name__ == "__main__":
    main()
