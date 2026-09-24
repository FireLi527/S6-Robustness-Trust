"""Read-only dashboard adapter for the frozen, specimen-grouped experiment."""
import hashlib
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from integrity_detector import assess_manifest
from manifest_protocol import load_candidate_manifest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/fruitfly_poisoning"
RESULTS = ROOT / "results/fruitfly_poisoning/grouped_defense_v1"
GROUPED = DATA / "grouped_defense_v1"
IMAGE_ROOT = DATA / "images"
DATASETS = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")

@lru_cache(maxsize=32)
def _read(path, stamp, size):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()

def document(path):
    s = path.stat()
    return _read(str(path), s.st_mtime_ns, s.st_size)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(actual, expected):
    if actual != expected:
        raise ValueError("Frozen fruit-fly artifacts changed; re-verify results before display")

def load_manifest(name):
    if name not in DATASETS:
        raise ValueError("Unknown dataset")
    return tuple(load_candidate_manifest(DATA / "manifests" / (name + ".csv")))

def validated():
    experiment, eh = document(GROUPED / "protocol.json")
    protocol, ph = document(DATA / "protocol.json")
    require(ph, experiment["dataset_protocol_sha256"])
    require(digest(DATA / "specimen_group_confirmation.json"), experiment["confirmation_sha256"])
    require(digest(Path(__file__).with_name("fruitfly_group_detector.py")), experiment["algorithm_sha256"])
    selection, sh = document(GROUPED / "detector_selection.json")
    plan, planh = document(GROUPED / "selection_plan.json")
    predictions, preh = document(RESULTS / "candidate_predictions.json")
    detection, _ = document(RESULTS / "detection_summary.json")
    for obj in (selection, plan, predictions):
        require(obj["experiment_sha256"], eh)
    for obj in (plan, predictions):
        require(obj["selection_sha256"], sh)
    require(preh, plan["predictions_sha256"])
    require(detection["selection_plan_sha256"], planh)
    require(detection["chosen"], selection["chosen"])
    for name in DATASETS:
        mh = digest(DATA / "manifests" / (name + ".csv"))
        require(mh, protocol["manifests"][name]["sha256"])
        require(mh, plan["variants"][name + "__semantic"]["source_manifest_sha256"])
    return predictions, detection, planh

def assessment_payload(name):
    if name not in DATASETS:
        raise ValueError("Unknown dataset")
    a = assess_manifest(DATA / "manifests/clean_subset.csv", DATA / "manifests" / (name + ".csv"))
    return {"dataset": name, **{key: getattr(a, key) for key in (
        "decision", "risk_score", "reasons", "candidate_samples", "label_changes", "hash_changes",
        "missing_samples", "unknown_samples", "duplicate_ids", "distribution_drift")}}

def class_names():
    return {str(i): line.split(maxsplit=1)[-1] for i, line in enumerate((IMAGE_ROOT / "classes.txt").read_text().splitlines())}

def semantic_payload(name):
    if name not in DATASETS:
        raise ValueError("Unknown dataset")
    predictions, detection, _ = validated()
    values = list(predictions["datasets"][name].values())
    m = next(m for m in detection["results"] if m["dataset"] == name)
    return {"dataset": name, "source": "grouped_defense_v1", "detector": detection["chosen"],
        "samples": len(values), "decision_counts": dict(Counter(v["decision"] for v in values)),
        "mean_risk_score": sum(v["risk_score"] for v in values) / len(values),
        "offline_evaluation": {"precision": m["precision"] if m["tp"] + m["fn"] else None,
            "recall": m["recall"], "f1": m["f1"] if m["tp"] + m["fn"] else None,
            "clean_false_positive_rate": m["clean_fpr"], "roc_auc": None}}

def semantic_result_by_sample_id(name, sample_id):
    predictions, detection, _ = validated()
    v = predictions["datasets"][name][sample_id]
    return {**v, "classifier_confidence": 1 - v["signals"][1], "neighbors": [], "reasons": [
        "Specimen-grouped out-of-fold classifier; risk = 1 - candidate-label confidence.",
        "REVIEW threshold: %.2f; neighbor and centroid signals are not used in the selected score." % detection["chosen"]["threshold"]]}

def training_payload():
    _, _, planh = validated()
    comparison, _ = document(RESULTS / "comparison.json")
    require(comparison["selection_plan_sha256"], planh)
    require(comparison["status"], "VERIFIED")
    require(len(comparison["rows"]), 12)
    return comparison
