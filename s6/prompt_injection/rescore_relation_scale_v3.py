"""Post-hoc diagnostic: rescore frozen v2-prompt outputs against v3 references, no inference.

Outputs were generated under the v2 prompt, which never asked for ``claims`` or the v3
mechanical norms, so v2 validity is kept and predictions get ``claims=[]``. Norms were
chosen after these outputs were seen; results can never be reported as model improvement.
"""
import json
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, write_json
from s6.prompt_injection.relation_contract_v3 import units
from s6.prompt_injection.relation_scale_metrics_v1 import ARMS, aggregate, coverage

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "results/bipia/relation_scale_evaluation_v1"
REFERENCES = ROOT / "data/bipia/relation_scale_targets_v3"


def rescore(prediction: dict, target: dict) -> dict:
    """Strict v3 unit comparison of an output that was valid under the frozen v2 contract."""
    gold = units(target)
    if not prediction["score"]["valid"]:
        return {"valid": False, "exact": False, "matched": 0, "predicted": 0, "reference": sum(gold.values())}
    predicted = units({**json.loads(prediction["text"]), "claims": []})
    return {"valid": True, "exact": predicted == gold, "matched": sum((predicted & gold).values()),
            "predicted": sum(predicted.values()), "reference": sum(gold.values())}


def check_inputs() -> dict:
    for status in (EVALUATION / "status.json", EVALUATION / "verification/status.json", REFERENCES / "status.json"):
        if read_json(status)["state"] != "COMPLETE":
            raise ValueError(f"Incomplete upstream artifact: {status}")
    verified = read_json(EVALUATION / "verification/protocol.json")["protected_sha256"]
    predictions = EVALUATION / "predictions.json"
    if file_sha256(predictions) != verified["results/bipia/relation_scale_evaluation_v1/predictions.json"]:
        raise ValueError("Frozen predictions changed")
    return {"predictions.json": file_sha256(predictions), "v3 samples.json": file_sha256(REFERENCES / "samples.json")}


def main() -> None:
    hashes = check_inputs()
    rows = [r for r in read_json(REFERENCES / "samples.json") if r["split"] == "validation"]
    lookup = {r["id"]: r for r in rows}
    predictions = read_json(EVALUATION / "predictions.json")
    coverage(predictions, rows)
    rescored = [{**p, "score": rescore(p, lookup[p["id"]]["targets"][p["side"]])} for p in predictions]
    v1 = read_json(EVALUATION / "summary.json")
    summary = {"post_hoc_diagnostic_only": True, "replaces_v1_metrics": False, "arms": {}}
    for arm in ARMS:
        summary["arms"][arm] = {}
        for variant in ("core", "layout"):
            ids = {r["id"] for r in rows if r["variant"] == variant}
            selected = [r for r in rows if r["id"] in ids]
            summary["arms"][arm][variant] = {"v1": v1[arm][variant],
                                             "v3": aggregate([p for p in rescored if p["arm"] == arm and p["id"] in ids], selected)}
    items = [{k: p[k] for k in ("arm", "id", "side", "score")} for p in rescored]
    code = {name: file_sha256(ROOT / "s6/prompt_injection" / name)
            for name in ("rescore_relation_scale_v3.py", "relation_contract_v3.py")}
    with new_run(ROOT / "results/bipia/relation_scale_v3_rescore_v1", {"inputs_sha256": hashes, "code_sha256": code,
                 "inference": False, "prediction_adaptation": "v2 validity kept; claims=[] added"}) as run:
        write_json(run / "scores.json", items)
        write_json(run / "summary.json", summary)
    print("V3 post-hoc rescore COMPLETE", flush=True)


if __name__ == "__main__":
    main()
