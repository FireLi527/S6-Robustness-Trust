"""Audit frozen references and scale-evaluation outputs without inference or rescoring."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, write_json
from s6.prompt_injection.relation_annotation_audit_v1 import (attribute_side, parse, reference_inventory,
                                                             summarize_attribution)
from s6.prompt_injection.relation_contract_v2 import units
from s6.prompt_injection.relation_scale_metrics_v1 import ARMS

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "results/bipia/relation_scale_evaluation_v1"
SAMPLES = ROOT / "data/bipia/relation_scale_training_v1/samples.json"


def frozen_hash(protocol: dict, path: Path) -> str:
    """Look up a protocol hash by repository-relative path in either separator style."""
    wanted = str(path.relative_to(ROOT)).replace("\\", "/")
    for name, digest in protocol["protected_sha256"].items():
        if name.replace("\\", "/") == wanted:
            return digest
    raise ValueError(f"No frozen hash recorded for {wanted}")


def check_inputs() -> dict:
    """Read only COMPLETE, verified artifacts whose hashes match their recorded values."""
    for status in (EVALUATION / "status.json", EVALUATION / "verification/status.json"):
        if read_json(status)["state"] != "COMPLETE":
            raise ValueError(f"Incomplete upstream artifact: {status}")
    verified = read_json(EVALUATION / "verification/protocol.json")
    hashes = {}
    for path, protocol in ((SAMPLES, read_json(EVALUATION / "protocol.json")),
                           (EVALUATION / "predictions.json", verified)):
        expected = frozen_hash(protocol, path)
        if file_sha256(path) != expected:
            raise ValueError(f"Frozen artifact changed: {path}")
        hashes[str(path.relative_to(ROOT)).replace("\\", "/")] = expected
    return hashes


def reference_sides(rows: list) -> list:
    """Core references only; identical task texts are counted once."""
    sides, seen = [], set()
    for row in rows:
        if row["variant"] != "core":
            continue
        for side in ("task", "content"):
            key = (side, row["inputs"][side])
            if key not in seen:
                seen.add(key)
                sides.append({"id": row["id"], "side": side, "split": row["split"], "target": row["targets"][side]})
    return sides


def attributions(rows: list, predictions: list) -> list:
    """Deduplicated validation side inputs per arm, matching the frozen evaluation denominator."""
    lookup, items, seen = {r["id"]: r for r in rows}, [], set()
    for p in predictions:
        row = lookup[p["id"]]
        key = (p["arm"], row["variant"], p["side"], row["inputs"][p["side"]])
        if key in seen:
            continue
        seen.add(key)
        target = row["targets"][p["side"]]
        items.append({"arm": p["arm"], "variant": row["variant"], "id": p["id"], "side": p["side"],
                      "strict_exact": p["score"]["exact"], "reference_units": sum(units(target).values()),
                      "attribution": attribute_side(parse(p), target)})
    return items


def main() -> None:
    hashes = check_inputs()
    rows, predictions = read_json(SAMPLES), read_json(EVALUATION / "predictions.json")
    sides = reference_sides(rows)
    items = attributions(rows, predictions)
    summary = {"development_diagnostic_only": True, "strict_scores_changed": False,
               "reference_inventory": {"all": reference_inventory(sides),
                                       "validation": reference_inventory([s for s in sides if s["split"] == "validation"])},
               "attribution": {arm: {variant: summarize_attribution(
                   [i for i in items if i["arm"] == arm and i["variant"] == variant])
                   for variant in ("core", "layout")} for arm in ARMS}}
    code = {name: file_sha256(ROOT / "s6/prompt_injection" / name)
            for name in ("relation_annotation_audit_v1.py", "audit_relation_annotation_v1.py")}
    protocol = {"inputs_sha256": hashes, "code_sha256": code, "inference": False, "training": False,
                "denominator": "per arm and variant, deduplicated side inputs: 6 tasks + 18 contents",
                "heuristics": "literal containment ladder; evidence field excluded from coverage"}
    with new_run(ROOT / "results/bipia/relation_annotation_audit_v1", protocol) as run:
        write_json(run / "items.json", items)
        write_json(run / "summary.json", summary)
    print("Relation annotation audit COMPLETE", flush=True)


if __name__ == "__main__":
    main()
