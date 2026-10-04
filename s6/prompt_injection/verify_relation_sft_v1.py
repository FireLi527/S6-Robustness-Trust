"""Reconstruct actual model requests, replay extraction scores and verify adapters."""
from pathlib import Path
import json
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_sft_io import messages, score, FEWSHOT_IDS

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "results/bipia/relation_sft_v1"
RUN = ROOT / "results/bipia/relation_sft_v1_evaluation"


def verify_predictions(rows: list[dict], predictions: list[dict], summary: dict) -> dict:
    """Fail for duplicate/missing calls, hidden oracle inputs or altered scoring."""
    lookup = {r["id"]: r for r in rows}
    examples = [lookup[identifier] for identifier in FEWSHOT_IDS]
    expected = {(r["id"], side, arm) for r in rows if r["split"] != "train"
                for side in ("task", "content") for arm in ("base_zero", "base_fewshot", "adapter_zero")}
    keys = [(p["id"], p["side"], p["arm"]) for p in predictions]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Missing or duplicated model calls")
    for p in predictions:
        row = lookup[p["id"]]
        supplied = messages(row, p["side"], examples if p["arm"] == "base_fewshot" else None)
        if p["input_messages"] != supplied or p["split"] != row["split"]:
            raise ValueError("Request reconstruction differs; possible oracle input")
        if p["input_tokens"] != len(p["input_ids"]) or p["output_tokens"] != len(p["generated_token_ids"]):
            raise ValueError("Token coverage counts differ")
        if p["input_tokens"] + 1200 > 4096 or p["output_tokens"] > 1200:
            raise ValueError("Generation budget breached")
        if score(p["text"], p["finished"], row["inputs"][p["side"]], row["targets"][p["side"]]) != p["score"]:
            raise ValueError("Raw text score replay differs")
    for split, arms in summary.items():
        for arm, stored in arms.items():
            group = [p for p in predictions if p["split"] == split and p["arm"] == arm]
            counts = {"side_samples": len(group), **{key: sum(p["score"][key] for p in group)
                      for key in ("valid", "mode_correct", "actions_exact", "fields_exact")}, "unfinished": sum(not p["finished"] for p in group)}
            if counts != stored:
                raise ValueError("Summary count differs")
    return {"calls_replayed": len(predictions), "no_oracle_in_current_input": True,
            "max_input_tokens": max(p["input_tokens"] for p in predictions),
            "max_output_tokens": max(p["output_tokens"] for p in predictions)}


def main() -> None:
    from transformers import AutoTokenizer
    if read_json(RUN / "status.json")["state"] != "COMPLETE":
        raise ValueError("Training/evaluation run is incomplete")
    protocol = read_json(RUN / "protocol.json")
    protected = {**protocol["protected_sha256"],
                 **{str(p.relative_to(ROOT)): file_sha256(p) for p in RUN.rglob("*.json") if "verification" not in p.parts}}
    for name, digest in protected.items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    completion = read_json(RUN / "completion.json")
    for name, digest in completion["adapter_sha256"].items():
        require_hash(TRAIN / name, digest)
    parameters = read_json(TRAIN / "parameters.json")
    if not parameters["trainable_names"] or any("lora_" not in name for name in parameters["trainable_names"]):
        raise ValueError("Unexpected trainable weights")
    rows = read_json(ROOT / "data/bipia/relation_sft_v1/samples.json")
    predictions = read_json(RUN / "predictions.json")
    tokenizer = AutoTokenizer.from_pretrained(str(ROOT / "external/qwen3_4b_train_v1"), local_files_only=True, trust_remote_code=False)
    with new_run(RUN / "verification", {"protected_sha256": protected, "code_sha256": file_sha256(Path(__file__))}):
        result = verify_predictions(rows, predictions, read_json(RUN / "summary.json"))
        for p in predictions:
            raw = read_json(RUN / "raw" / f"{p['id']}_{p['side']}_{p['arm']}.json")
            if raw != p:
                raise ValueError("Consolidated prediction differs from raw response")
            tokens = tokenizer.apply_chat_template(p["input_messages"], tokenize=True, return_dict=False,
                                                   add_generation_prompt=True, enable_thinking=False)
            if tokens != p["input_ids"] or tokenizer.decode(p["generated_token_ids"], skip_special_tokens=True) != p["text"]:
                raise ValueError("Input/output token reconstruction differs")
            ended = bool(p["generated_token_ids"]) and p["generated_token_ids"][-1] == tokenizer.eos_token_id
            if ended != p["finished"]:
                raise ValueError("EOS status differs")
        trace = read_json(TRAIN / "training_trace.json")
        if len(trace) != completion["optimizer_steps"] or {p["epoch"] for p in trace} != {1, 2, 3}:
            raise ValueError("Training schedule mismatch")
        write_json(RUN / "verification/result.json", {**result, "adapter_hashes_verified": True,
                   "optimizer_steps": len(trace), "only_lora_trainable": True})
    print("SFT verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
