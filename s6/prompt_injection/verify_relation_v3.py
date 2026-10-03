"""Replay one v3 evaluation phase offline: inputs, tokens, EOS, scores and summary; no inference."""
import argparse
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection import relation_sft_v2_io as v2_io
from s6.prompt_injection import relation_sft_v3_io as v3_io
from s6.prompt_injection.evaluate_relation_v3 import (DATA, HOLDOUT, MODEL, OUT, TRAIN, add_claims_free, summarize,
                                                      unique_jobs, v1_score)


def verify_record(p: dict, row: dict, examples: list, tokenizer) -> None:
    io = v2_io if p["arm"] == "v1_large_28" else v3_io
    demos = examples if p["arm"] == "base_fewshot_v3" else None
    if p["input_ids"] != io.tokens(tokenizer, row, p["side"], demos):
        raise ValueError(f"Input mismatch: {p['arm']} {p['id']} {p['side']}")
    generated = p["generated_token_ids"]
    if tokenizer.decode(generated, skip_special_tokens=True) != p["text"]:
        raise ValueError("Output token mismatch")
    finished = bool(generated) and generated[-1] == tokenizer.eos_token_id
    target = row["targets"][p["side"]]
    base = (v1_score(p["text"], finished, row, p["side"]) if p["arm"] == "v1_large_28"
            else v3_io.score_text(p["text"], finished, row["inputs"][p["side"]], target))
    if p["finished"] != finished or p["score"] != add_claims_free(base, p["text"], target):
        raise ValueError("EOS or score mismatch")
    if len(p["input_ids"]) + 1600 > 4096 or not 0 < len(generated) <= 1600:
        raise ValueError("Token budget mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("validation", "holdout"), required=True)
    phase = parser.parse_args().phase
    from transformers import AutoTokenizer
    run = OUT / phase
    if read_json(run / "status.json")["state"] != "COMPLETE":
        raise ValueError("Incomplete evaluation phase")
    protocol = read_json(run / "protocol.json")
    for name, digest in protocol["code_sha256"].items():
        require_hash(Path(__file__).parent / name, digest)
    if file_sha256(TRAIN / "protocol.json") != protocol["training_protocol_sha256"]:
        raise ValueError("Training protocol changed")
    all_rows = read_json(DATA / "samples.json")
    rows = [r for r in all_rows if r["split"] == "validation"] if phase == "validation" else read_json(HOLDOUT)
    lookup = {r["id"]: r for r in rows}
    examples = [next(r for r in all_rows if r["id"] == read_json(TRAIN / "protocol.json")["fewshot_ids"][0])]
    predictions = read_json(run / "predictions.json")
    expected = {(r["id"], s, a) for r in rows for s in ("task", "content") for a in protocol["arms"]}
    keys = [(p["id"], p["side"], p["arm"]) for p in predictions]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Prediction coverage mismatch")
    raw = {f"{a}_{r['id']}_{s}.json" for a in protocol["arms"] for r, s in unique_jobs(rows)}
    if {p.name for p in (run / "raw").glob("*.json")} != raw:
        raise ValueError("Distinct call coverage mismatch")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    for p in predictions:
        verify_record(p, lookup[p["id"]], examples, tokenizer)
        stored = read_json(run / "raw" / f"{p['arm']}_{p['inference_id']}_{p['side']}.json")
        if {**stored, "id": p["id"], "inference_id": stored["id"]} != p:
            raise ValueError("Raw/expanded record mismatch")
    if summarize(predictions, rows, protocol["arms"]) != read_json(run / "summary.json"):
        raise ValueError("Summary mismatch")
    protected = {str(p.relative_to(run)).replace("\\", "/"): file_sha256(p) for p in run.rglob("*.json")}
    with new_run(run / "verification", {"protected_sha256": protected, "code_sha256": file_sha256(Path(__file__))}):
        write_json(run / "verification/result.json", {"distinct_calls_replayed": len(raw), "expanded_records": len(predictions),
                   "new_inference_during_verification": False})
    print(f"V3 {phase} verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
