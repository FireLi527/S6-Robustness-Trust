"""Qwen3-4B direct-versus-extracted authorization pilot, no training."""
from pathlib import Path
import time
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.instruction_slot_model import request, metadata
from s6.prompt_injection.instruction_slot_data import build_rows
from s6.prompt_injection.instruction_slot_evaluation import prediction, summarize_arm

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/instruction_slots_v1"
DATA = ROOT / "data/bipia/instruction_slots_v1"


def main() -> None:
    design = read_json(ROOT / "data/bipia/instruction_slots_v1_design/protocol.json")
    protected = {**read_json(ROOT / "results/bipia/authorization_slots_v1/protocol.json")["protected_sha256"],
                 **design["protected_sha256"]}
    for name in ("instruction_slot_data.py", "instruction_slot_evaluation.py", "experiment_instruction_slots_v1.py"):
        path = "s6/prompt_injection/" + name
        protected[path] = file_sha256(ROOT / path)
    for path, digest in protected.items():
        require_hash(ROOT / path, digest)
    rows = build_rows()
    with new_run(DATA, {"design": design, "protected_sha256": protected, "labels": "32 programmatic English cases; NOT human-reviewed"}):
        write_json(DATA / "samples.json", rows)
    model = metadata()
    protocol = {"protected_sha256": protected, "data_sha256": file_sha256(DATA / "samples.json"),
                "model": model, "design": design, "calls": "32 x (direct + separate task/content extraction) = 96",
                "tools": "none", "oracle_input": False, "training": False,
                "order": "alternate direct-first and extraction-first by row index", "retry_or_prompt_repair": False}
    with new_run(OUT, protocol):
        all_predictions = {arm: [] for arm in ("direct", "structured")}
        timings = []
        for index, row in enumerate(rows):
            records = {}
            order = ("direct", "task", "content") if index % 2 == 0 else ("task", "content", "direct")
            for mode in order:
                started = time.perf_counter()
                records[mode] = request(mode, row["content"] if mode == "content" else row["task"], row["content"] if mode == "direct" else "")
                timings.append({"id": row["id"], "mode": mode, "seconds": time.perf_counter() - started,
                                "prompt_tokens": records[mode]["response"].get("prompt_eval_count"),
                                "output_tokens": records[mode]["response"].get("eval_count"),
                                "done_reason": records[mode]["response"].get("done_reason")})
                write_json(OUT / "raw" / f"{index:02d}_{mode}.json", records[mode])
            for arm in all_predictions:
                all_predictions[arm].append(prediction(row, records, arm))
            print(f"Completed row {index + 1}/32", flush=True)
        for arm, predictions in all_predictions.items():
            write_json(OUT / f"{arm}_predictions.json", predictions)
        write_json(OUT / "summary.json", {arm: summarize_arm(rows, p, arm) for arm, p in all_predictions.items()})
        write_json(OUT / "timings.json", timings)
        metadata()
        for path, digest in protected.items():
            require_hash(ROOT / path, digest)
        require_hash(DATA / "samples.json", protocol["data_sha256"])
        write_json(OUT / "integrity.json", {"protected_files": len(protected), "raw_responses": len(timings),
                                           "data_sha256": protocol["data_sha256"]})
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
