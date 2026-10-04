"""Replay every distinct generation and expanded score, without GPU inference."""
from pathlib import Path
from transformers import AutoTokenizer
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_scale_metrics_v1 import ARMS, coverage, jobs, summarize
from s6.prompt_injection.relation_sft_v2_io import messages, tokens, score_text

ROOT = Path(__file__).resolve().parents[2]


def verify_record(p: dict, row: dict, examples: list, tokenizer) -> None:
    """Reconstruct request, tokenization, EOS, strict score and budget."""
    side = p["side"]
    demos = examples if p["arm"] == "base_fewshot" else None
    if p["input_messages"] != messages(row, side, demos) or p["input_ids"] != tokens(tokenizer, row, side, demos):
        raise ValueError("Input provenance mismatch")
    generated = p["generated_token_ids"]
    if tokenizer.decode(generated, skip_special_tokens=True) != p["text"]:
        raise ValueError("Output token mismatch")
    finished = bool(generated) and generated[-1] == tokenizer.eos_token_id
    if p["finished"] != finished or p["score"] != score_text(p["text"], finished, row["inputs"][side], row["targets"][side]):
        raise ValueError("EOS or score mismatch")
    if p["input_tokens"] != len(p["input_ids"]) or p["output_tokens"] != len(generated):
        raise ValueError("Token count mismatch")
    if p["input_tokens"] + 1600 > 4096 or not 0 < len(generated) <= 1600:
        raise ValueError("Token budget mismatch")


def main() -> None:
    run = ROOT / "results/bipia/relation_scale_evaluation_v1"
    if read_json(run / "status.json")["state"] != "COMPLETE":
        raise ValueError("Incomplete evaluation")
    protocol = read_json(run / "protocol.json")
    for name, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    model = ROOT / "external/qwen3_4b_train_v1"
    for name, digest in protocol["model_files_sha256"].items():
        require_hash(model / name, digest)
    all_rows = read_json(ROOT / "data/bipia/relation_scale_training_v1/samples.json")
    lookup = {r["id"]: r for r in all_rows}
    rows = [r for r in all_rows if r["split"] == "validation"]
    examples = [lookup[i] for i in protocol["fewshot_ids"]]
    predictions = read_json(run / "predictions.json")
    coverage(predictions, rows)
    tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
    expected_files = {f"{arm}_{r['id']}_{s}.json" for arm in ARMS for r, s in jobs(rows)}
    if {p.name for p in (run / "raw").glob("*.json")} != expected_files:
        raise ValueError("Distinct call coverage mismatch")
    for p in predictions:
        verify_record(p, lookup[p["id"]], examples, tokenizer)
        raw = read_json(run / "raw" / f"{p['arm']}_{p['inference_id']}_{p['side']}.json")
        if {**raw, "id": p["id"], "inference_id": raw["id"]} != p:
            raise ValueError("Raw/reused record mismatch")
        if lookup[p["id"]]["inputs"][p["side"]] != lookup[p["inference_id"]]["inputs"][p["side"]]:
            raise ValueError("Wrong duplicate provenance")
    for arm in ARMS:
        if read_json(run / f"{arm}_predictions.json") != [p for p in predictions if p["arm"] == arm]:
            raise ValueError("Arm/consolidated mismatch")
    if summarize(predictions, rows) != read_json(run / "summary.json"):
        raise ValueError("Summary mismatch")
    protected = {str(p.relative_to(ROOT)): file_sha256(p) for p in run.rglob("*.json")}
    with new_run(run / "verification", {"protected_sha256": protected, "code_sha256": file_sha256(Path(__file__))}):
        write_json(run / "verification/result.json", {"distinct_calls_replayed": len(expected_files),
                   "expanded_records_replayed": len(predictions), "hashes_verified": True,
                   "development_only": True, "new_inference_during_verification": False})
    print("Scale evaluation verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
