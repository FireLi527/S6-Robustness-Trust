"""Independently count selective decisions and audit field equality/coverage."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.authorization_slots import decide

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/bipia/authorization_slots_v1"


def verify_group(rows: list[dict], predictions: list[dict], metrics: dict) -> dict:
    """Use explicit independent counts, never the original summary helper."""
    if len(rows) != len(predictions):
        raise ValueError("Mismatched rows")
    by_label = {0: {"NORMAL": 0, "RISK": 0, "REVIEW": 0},
                1: {"NORMAL": 0, "RISK": 0, "REVIEW": 0},
                None: {"NORMAL": 0, "RISK": 0, "REVIEW": 0}}
    field_counts = {side: [0, 0, 0] for side in ("task", "content")}
    both_counts = [0, 0, 0]
    for row, saved in zip(rows, predictions, strict=True):
        repeated = {"id": row["id"], **decide(row["task"], row["content"])}
        if repeated != saved or saved["tool_authorization"] != "not_granted":
            raise ValueError("Text-only prediction replay mismatch")
        by_label[row["label"]][saved["decision"]] += 1
        expected = row.get("expected_slots")
        if expected is None:
            continue
        for side in ("task", "content"):
            truth, predicted = expected[side], saved[f"{side}_slots"]
            if truth is not None:
                field_counts[side][0] += 1
                field_counts[side][1] += predicted is not None
                field_counts[side][2] += predicted == truth
        if all(expected[side] is not None for side in ("task", "content")):
            both_counts[0] += 1
            both_counts[1] += all(saved[f"{side}_slots"] is not None for side in ("task", "content"))
            both_counts[2] += all(expected[side] == saved[f"{side}_slots"] for side in ("task", "content"))
    risky, normal, unknown = by_label[1], by_label[0], by_label[None]
    automatic = risky["RISK"] + risky["NORMAL"] + normal["RISK"] + normal["NORMAL"]
    known = sum(risky.values()) + sum(normal.values())
    checks = {"known_labels": known, "unknown_labels": sum(unknown.values()),
              "true_auto_risk": risky["RISK"], "false_auto_risk": normal["RISK"],
              "risk_auto_normal": risky["NORMAL"], "risk_review": risky["REVIEW"], "normal_review": normal["REVIEW"],
              "risk_count": sum(risky.values()), "normal_count": sum(normal.values()),
              "coverage_all": 1 - sum(counts["REVIEW"] for counts in by_label.values()) / len(rows),
              "coverage_known": automatic / known if known else None,
              "selective_accuracy": (risky["RISK"] + normal["NORMAL"]) / automatic if automatic else None,
              "risk_auto_recall": risky["RISK"] / sum(risky.values()) if sum(risky.values()) else None,
              "normal_auto_fpr": normal["RISK"] / sum(normal.values()) if sum(normal.values()) else None}
    if any(metrics[k] != v for k, v in checks.items()):
        raise ValueError("Selective metric mismatch")
    for side, counts in {**field_counts, "both": both_counts}.items():
        item = metrics["extraction"][side]
        if [item["eligible"], item["extracted"], item["exact_correct"]] != counts:
            raise ValueError("Slot extraction count mismatch")
    return {"predictions_repeated": len(rows), "counts_by_label": {str(k): v for k, v in by_label.items()},
            "slot_counts": field_counts, "both_slot_counts": both_counts}


def main() -> None:
    protocol = read_json(RUN / "protocol.json")
    for path, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / path, digest)
    data_path = ROOT / "data/bipia/authorization_slots_v1/samples.json"
    require_hash(data_path, protocol["samples_sha256"])
    rows = read_json(data_path)
    groups = {section: [r for r in rows if r["section"] == section]
              for section in ("grammar_contract", "wording_holdout", "boundary_pressure")}
    groups["seen540"] = read_json(ROOT / "data/bipia/authorization_relation_v1/samples.json")
    groups["reviewed60"] = [r for r in read_json(ROOT / "data/bipia/authorization_probe_v1/samples.json")
                            if r["split"] == "synthetic_diagnostic"]
    summary = read_json(RUN / "summary.json")
    bound = {str(p.relative_to(ROOT)): file_sha256(p) for p in RUN.iterdir() if p.is_file()}
    with new_run(RUN / "verification", {"code_sha256": file_sha256(Path(__file__)), "artifacts_sha256": bound}):
        results = {name: verify_group(subset, read_json(RUN / f"{name}_predictions.json"), summary[name])
                   for name, subset in groups.items()}
        for path, digest in {**bound, **protocol["protected_sha256"]}.items():
            require_hash(ROOT / path, digest)
        write_json(RUN / "verification/result.json", results)
    print("Verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
