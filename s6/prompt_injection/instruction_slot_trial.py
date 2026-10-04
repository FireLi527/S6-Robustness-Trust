"""Shared trial runner for frozen extraction arms and an unchanged direct control."""
from pathlib import Path
import time
from s6.engineering.artifacts import new_run, require_hash, write_json
from s6.prompt_injection.instruction_slot_model import request, metadata
from s6.prompt_injection.instruction_slot_fewshot import request as fewshot_request
from s6.prompt_injection.instruction_slot_evaluation import prediction, summarize_arm

ARMS = ("direct", "structured_v1", "structured_v2")


def run_trial(root: Path, out: Path, rows: list[dict], protocol: dict, arms: tuple[str, ...]) -> None:
    """Alternate inference order, persist every response, retain all abstentions."""
    if not rows or not arms or any(arm not in ARMS for arm in arms):
        raise ValueError("Empty trial or unsupported arm")
    protected = protocol["protected_sha256"]
    for name, digest in protected.items():
        require_hash(root / name, digest)
    model = metadata()
    with new_run(out, {**protocol, "model": model, "arms": arms, "tools": "none", "training": False,
                       "retry_or_prompt_repair": False, "evaluation_oracle_input": False}):
        predictions = {arm: [] for arm in arms}
        timings = []
        for index, row in enumerate(rows):
            for arm in arms if index % 2 == 0 else tuple(reversed(arms)):
                records = {}
                for mode in (("direct",) if arm == "direct" else ("task", "content")):
                    started = time.perf_counter()
                    source = row["content"] if mode == "content" else row["task"]
                    records[mode] = (fewshot_request(mode, source) if arm == "structured_v2" else
                                     request(mode, source, row["content"] if mode == "direct" else ""))
                    response = records[mode]["response"]
                    timings.append({"id": row["id"], "arm": arm, "mode": mode,
                                    "seconds": time.perf_counter() - started,
                                    "prompt_tokens": response.get("prompt_eval_count"),
                                    "output_tokens": response.get("eval_count"), "done_reason": response.get("done_reason")})
                    write_json(out / "raw" / f"{index:02d}_{arm}_{mode}.json", records[mode])
                predictions[arm].append(prediction(row, records, "direct" if arm == "direct" else "structured"))
            print(f"{out.name}: {index + 1}/{len(rows)}", flush=True)
        for arm, values in predictions.items():
            write_json(out / f"{arm}_predictions.json", values)
        write_json(out / "summary.json", {arm: summarize_arm(rows, values, "direct" if arm == "direct" else "structured")
                                          for arm, values in predictions.items()})
        write_json(out / "timings.json", timings)
        metadata()
        for name, digest in protected.items():
            require_hash(root / name, digest)
        write_json(out / "integrity.json", {"protected_files": len(protected), "raw_responses": len(timings)})
