"""Raw-response replay, independent selective counts and small stability audit."""
from pathlib import Path
import json
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.instruction_slot_model import request, metadata
from s6.prompt_injection.instruction_slot_evaluation import prediction

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/bipia/instruction_slots_v1"


def recount(rows: list[dict], predictions: list[dict], summary: dict, arm: str) -> None:
    """Explicit counts independent of the experiment's summary functions."""
    pairs = list(zip(rows, predictions, strict=True))
    auto = [(r, p) for r, p in pairs if p["decision"] != "REVIEW"]
    tp = sum(r["label"] == 1 and p["decision"] == "RISK" for r, p in pairs)
    fp = sum(r["label"] == 0 and p["decision"] == "RISK" for r, p in pairs)
    risk = sum(r["label"] for r in rows)
    normal = len(rows) - risk
    counts = {"coverage_all": len(auto) / len(rows), "true_auto_risk": tp, "false_auto_risk": fp,
              "risk_auto_recall": tp / risk, "normal_auto_fpr": fp / normal,
              "risk_auto_normal": sum(r["label"] == 1 and p["decision"] == "NORMAL" for r, p in pairs),
              "risk_review": sum(r["label"] == 1 and p["decision"] == "REVIEW" for r, p in pairs),
              "normal_review": sum(r["label"] == 0 and p["decision"] == "REVIEW" for r, p in pairs),
              "selective_accuracy": sum((p["decision"] == "RISK") == bool(r["label"]) for r, p in auto) / len(auto) if auto else None}
    if any(summary[k] != value for k, value in counts.items()):
        raise ValueError("Independent metric mismatch")
    if arm == "structured":
        for side in ("task", "content"):
            present = [(r["expected_slots"][side], p[f"{side}_slots"]) for r, p in pairs if p[f"{side}_slots"] is not None]
            stored = summary["extraction"][side]
            if stored["extracted"] != len(present) or stored["exact_correct"] != sum(a == b for a, b in present):
                raise ValueError("Slot exact match count mismatch")
            for field in ("mode", "operation", "target"):
                if stored["fields"][field]["correct"] != sum(a[field] == b[field] for a, b in present):
                    raise ValueError("Field count mismatch")


def main() -> None:
    protocol = read_json(RUN / "protocol.json")
    for path, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / path, digest)
    path = ROOT / "data/bipia/instruction_slots_v1/samples.json"
    require_hash(path, protocol["data_sha256"])
    rows = read_json(path)
    summary = read_json(RUN / "summary.json")
    saved = {arm: read_json(RUN / f"{arm}_predictions.json") for arm in ("direct", "structured")}
    bound = {str(p.relative_to(ROOT)): file_sha256(p) for p in RUN.rglob("*.json") if "verification" not in p.parts}
    metadata()
    with new_run(RUN / "verification", {"artifacts_sha256": bound, "code_sha256": file_sha256(Path(__file__)),
                                        "stability_sample": "first four rows, all three modes; never replace original responses"}):
        token_max, output_max = 0, 0
        for index, row in enumerate(rows):
            records = {mode: read_json(RUN / "raw" / f"{index:02d}_{mode}.json") for mode in ("direct", "task", "content")}
            for mode, record in records.items():
                supplied = json.loads(record["request"]["messages"][1]["content"])
                expected = {"user_task": row["task"], "document": row["content"]} if mode == "direct" else {"role": mode, "text": row["task"] if mode == "task" else row["content"]}
                if supplied != expected:
                    raise ValueError("Text input changed or oracle fields leaked")
                token_max = max(token_max, record["response"]["prompt_eval_count"])
                output_max = max(output_max, record["response"]["eval_count"])
            for arm in saved:
                if prediction(row, records, arm) != saved[arm][index]:
                    raise ValueError("Raw-response decision replay mismatch")
        for arm in saved:
            recount(rows, saved[arm], summary[arm], arm)
            for kind in {r["kind"] for r in rows}:
                indices = [i for i, r in enumerate(rows) if r["kind"] == kind]
                recount([rows[i] for i in indices], [saved[arm][i] for i in indices], summary[arm]["by_kind"][kind], "direct")
        stability = []
        for index, row in enumerate(rows[:4]):
            for mode in ("direct", "task", "content"):
                record = request(mode, row["content"] if mode == "content" else row["task"], row["content"] if mode == "direct" else "")
                old = read_json(RUN / "raw" / f"{index:02d}_{mode}.json")
                write_json(RUN / "verification" / f"repeat_{index}_{mode}.json", record)
                stability.append({"index": index, "mode": mode, "same_content": record["response"]["message"]["content"] == old["response"]["message"]["content"]})
        for path, digest in {**bound, **protocol["protected_sha256"]}.items():
            require_hash(ROOT / path, digest)
        write_json(RUN / "verification/result.json", {"decisions_replayed": 64, "raw_responses": 96,
                   "max_prompt_tokens": token_max, "max_output_tokens": output_max, "stability": stability})
    print("Verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
