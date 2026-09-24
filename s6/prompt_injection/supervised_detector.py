"""Opt-in research classifier; never grants tool permissions or automatic BLOCK."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from supervised_data import ROOT, model_text

ARTIFACT = ROOT / "results/bipia/supervised/model.joblib"
SELECTION = ARTIFACT.with_name("selection.json")

@lru_cache(maxsize=1)
def _load(model_mtime, selection_mtime):
    import joblib
    selection=json.loads(SELECTION.read_text(encoding="utf-8"))
    fingerprint=hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    if fingerprint!=selection["model_sha256"]:
        raise ValueError("Supervised model checksum mismatch")
    bundle=joblib.load(ARTIFACT)
    if bundle["threshold"]!=selection["threshold"]:
        raise ValueError("Supervised threshold mismatch")
    expected=bundle["protocol"]["code_hashes"]["supervised_data.py"]
    if hashlib.sha256(Path(__file__).with_name("supervised_data.py").read_bytes()).hexdigest()!=expected:
        raise ValueError("Supervised preprocessing changed since training")
    return bundle,fingerprint

def assess_supervised(question: str, text: str) -> dict:
    if not isinstance(question,str) or not question.strip() or not isinstance(text,str) or not text.strip():
        raise ValueError("Supervised evaluation requires a real task and nonempty content")
    bundle,fingerprint=_load(ARTIFACT.stat().st_mtime_ns,SELECTION.stat().st_mtime_ns)
    features=bundle["vectorizer"].transform([model_text(question,text)])
    score=float(bundle["model"].predict_proba(features)[0,1])
    return dict(detector="s6-supervised-hash-logistic",version="0.1.0",config_hash=fingerprint,
                decision="REVIEW" if score>=bundle["threshold"] else "ALLOW",score=score,
                threshold=bundle["threshold"],mode="experimental_observation_only",
                reasons=["Learned classifier score compared with a validation-selected threshold; score is not a calibrated attack probability."],
                affects_tool_policy=False)
