"""Replay raw outputs and frozen request/token/adapter provenance, offline."""
from pathlib import Path
from transformers import AutoTokenizer
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_sft_v2_io import messages, tokens, score_text, summarize

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    run = ROOT / "results/bipia/relation_sft_v2"
    if read_json(run / "status.json")["state"] != "COMPLETE":
        raise ValueError("Incomplete experiment")
    protocol = read_json(run / "protocol.json")
    for name, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    for name, digest in read_json(run / "training_complete.json")["adapter_sha256"].items():
        require_hash(run / name.replace("\\", "/"), digest)
    rows = read_json(ROOT / "data/bipia/relation_sft_v2/samples.json")
    lookup = {r["id"]: r for r in rows}
    examples = [lookup[i] for i in protocol["fewshot_ids"]]
    selected = [r for r in rows if r["split"] == "validation"]
    predictions = read_json(run / "predictions.json")
    expected = {(r["id"], side, arm) for r in selected for side in ("task", "content")
                for arm in ("base_zero", "base_fewshot", "adapter_zero")}
    keys = [(p["id"], p["side"], p["arm"]) for p in predictions]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Missing or duplicate predictions")
    tokenizer = AutoTokenizer.from_pretrained(str(ROOT / "external/qwen3_4b_train_v1"), local_files_only=True, trust_remote_code=False)
    for p in predictions:
        row, side = lookup[p["id"]], p["side"]
        demos = examples if p["arm"] == "base_fewshot" else None
        if messages(row, side, demos) != p["input_messages"] or tokens(tokenizer, row, side, demos) != p["input_ids"]:
            raise ValueError("Input mismatch")
        if tokenizer.decode(p["generated_token_ids"], skip_special_tokens=True) != p["text"]:
            raise ValueError("Output token mismatch")
        finished = bool(p["generated_token_ids"]) and p["generated_token_ids"][-1] == tokenizer.eos_token_id
        if finished != p["finished"] or score_text(p["text"], finished, row["inputs"][side], row["targets"][side]) != p["score"]:
            raise ValueError("Score or EOS mismatch")
        if len(p["input_ids"]) != p["input_tokens"] or len(p["generated_token_ids"]) != p["output_tokens"]:
            raise ValueError("Token count mismatch")
        if p["input_tokens"] + 1600 > 4096 or p["output_tokens"] > 1600:
            raise ValueError("Token budget mismatch")
        if read_json(run / "raw" / f"{p['id']}_{side}_{p['arm']}.json") != p:
            raise ValueError("Raw/consolidated mismatch")
    if summarize(predictions, selected) != read_json(run / "summary.json"):
        raise ValueError("Summary mismatch")
    trace = read_json(run / "training_trace.json")
    expected_steps = 3 * ((protocol["train_unique_sides"] + 3) // 4)
    if len(trace) != expected_steps or {r["epoch"] for r in trace} != {1, 2, 3}:
        raise ValueError("Training schedule mismatch")
    protected = {str(p.relative_to(ROOT)): file_sha256(p) for p in run.rglob("*.json")}
    with new_run(run / "verification", {"protected_sha256": protected, "code_sha256": file_sha256(Path(__file__))}):
        write_json(run / "verification/result.json", {"calls_replayed": len(predictions), "adapter_hashes_verified": True,
                   "optimizer_steps": len(trace), "development_only": True})
    print("V2 verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
