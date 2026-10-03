"""Pre-registered v3 evaluation: exposed development validation, then the sealed holdout exactly once."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection import relation_sft_v2_io as v2_io
from s6.prompt_injection import relation_sft_v3_io as v3_io
from s6.prompt_injection.relation_contract_v2 import validate as validate_v2
from s6.prompt_injection.relation_contract_v3 import units
from s6.prompt_injection.relation_scale_metrics_v1 import aggregate

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "external/qwen3_4b_train_v1"
DATA = ROOT / "data/bipia/relation_scale_training_v3"
HOLDOUT = ROOT / "data/bipia/relation_holdout_v3/samples.json"
TRAIN = ROOT / "results/bipia/relation_scale_training_v3"
V1_ADAPTER = ROOT / "results/bipia/relation_scale_training_v1/large_28/adapter"
OUT = ROOT / "results/bipia/relation_v3_evaluation"


def unique_jobs(rows: list) -> list:
    """One inference per distinct side text; conflicting references are rejected."""
    seen = {}
    for row in rows:
        for side in ("task", "content"):
            key = (side, row["inputs"][side])
            if key in seen and seen[key][0]["targets"][side] != row["targets"][side]:
                raise ValueError("Conflicting duplicate reference")
            seen.setdefault(key, (row, side))
    return list(seen.values())


def without_claims(counter):
    return {k: v for k, v in counter.items() if k[0] != "claims"}


def add_claims_free(score: dict, text: str, expected: dict) -> dict:
    """Secondary units excluding claims, so v1 outputs are not penalised for a field they never saw."""
    gold = without_claims(units(expected))
    result = {**score, "reference_no_claims": sum(gold.values()), "matched_no_claims": 0, "predicted_no_claims": 0}
    if score["valid"]:
        value = json.loads(text)
        predicted = without_claims(units({**value, "claims": value.get("claims", [])}))
        result["matched_no_claims"] = sum(min(n, gold.get(k, 0)) for k, n in predicted.items())
        result["predicted_no_claims"] = sum(predicted.values())
    return result


def generate(model, ids: list, tokenizer) -> dict:
    import torch
    if len(ids) + 1600 > 4096:
        raise ValueError("Full input/output budget exceeded; no truncation")
    inputs = torch.tensor([ids], device="cuda")
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        output = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=1600,
                                do_sample=False, pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id)
    generated = output[0, len(ids):].tolist()
    return {"text": tokenizer.decode(generated, skip_special_tokens=True), "input_ids": ids, "generated_token_ids": generated,
            "finished": bool(generated) and generated[-1] == tokenizer.eos_token_id}


def v1_score(text: str, finished: bool, row: dict, side: str) -> dict:
    try:
        value = json.loads(text) if finished else None
        validate_v2(value, row["inputs"][side])
        valid = True
    except (TypeError, ValueError):
        valid = False
    return v3_io.score_v2_output({"valid": valid}, text, row["targets"][side])


def run_arm(model, tokenizer, rows: list, arm: str, examples: list, out: Path) -> list:
    """v3 arms use the v3 prompt; v1_large_28 uses its own frozen v2 prompt."""
    io = v2_io if arm == "v1_large_28" else v3_io
    demos = examples if arm == "base_fewshot_v3" else None
    cache = {}
    for index, (row, side) in enumerate(unique_jobs(rows), 1):
        context = model.disable_adapter() if arm.startswith("base_") else nullcontext()
        with context:
            result = generate(model, io.tokens(tokenizer, row, side, demos), tokenizer)
        score = (v1_score(result["text"], result["finished"], row, side) if arm == "v1_large_28"
                 else v3_io.score_text(result["text"], result["finished"], row["inputs"][side], row["targets"][side]))
        call = {"id": row["id"], "side": side, "arm": arm, **result,
                "score": add_claims_free(score, result["text"], row["targets"][side])}
        write_json(out / "raw" / f"{arm}_{row['id']}_{side}.json", call)
        cache[(side, row["inputs"][side])] = call
        print(f"{arm}: {index} {row['id']} {side}", flush=True)
    return [{**cache[(s, r["inputs"][s])], "id": r["id"], "inference_id": cache[(s, r["inputs"][s])]["id"]}
            for r in rows for s in ("task", "content")]


def summarize(predictions: list, rows: list, arms: list) -> dict:
    """Same deduplicated denominators as v1, plus claims-excluded units."""
    lookup, result = {r["id"]: r for r in rows}, {}
    for arm in arms:
        result[arm] = {}
        for variant in ("core", "layout"):
            selected = [r for r in rows if r["variant"] == variant]
            ids = {r["id"] for r in selected}
            chosen = [p for p in predictions if p["arm"] == arm and p["id"] in ids]
            unique = {(p["side"], lookup[p["id"]]["inputs"][p["side"]]): p for p in chosen}.values()
            free = {k: sum(p["score"][k + "_no_claims"] for p in unique) for k in ("matched", "predicted", "reference")}
            result[arm][variant] = {**aggregate(chosen, selected), "claims_excluded_units": free}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("validation", "holdout"), required=True)
    phase = parser.parse_args().phase
    from transformers import AutoTokenizer
    from s6.prompt_injection.relation_sft_runtime import load_model
    if read_json(TRAIN / "status.json")["state"] != "COMPLETE":
        raise ValueError("V3 training incomplete")
    training = read_json(TRAIN / "protocol.json")
    adapters = [f"{arm}_v3" for arm in training["arms"]]
    if phase == "holdout" and read_json(OUT / "validation/verification/status.json")["state"] != "COMPLETE":
        raise ValueError("Holdout opens only after verified development validation")
    out = OUT / phase
    if out.exists():
        raise FileExistsError("Evaluation phase exists; never rerun or overwrite")
    for key, digest in training["protected_sha256"].items():
        require_hash(ROOT / key, digest)
    all_rows = read_json(DATA / "samples.json")
    examples = [next(r for r in all_rows if r["id"] == training["fewshot_ids"][0])]
    rows = [r for r in all_rows if r["split"] == "validation"] if phase == "validation" else read_json(HOLDOUT)
    arms = ["base_zero_v3", "base_fewshot_v3", *adapters] + (["v1_large_28"] if phase == "holdout" else [])
    code = {n: file_sha256(ROOT / "s6/prompt_injection" / n) for n in ("evaluate_relation_v3.py", "relation_sft_v3_io.py",
            "relation_contract_v3.py", "relation_sft_v2_io.py", "relation_contract_v2.py")}
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    with new_run(out, {"phase": phase, "arms": arms, "code_sha256": code, "rows": len(rows),
                       "training_protocol_sha256": file_sha256(TRAIN / "protocol.json"),
                       "plan": read_json(DATA / "protocol.json")["evaluation_plan"]}):
        model = load_model(MODEL)
        model.gradient_checkpointing_disable()
        model.config.use_cache = True
        for name, path in [(a, TRAIN / a.removesuffix("_v3") / "adapter") for a in adapters] + \
                          ([("v1_large_28", V1_ADAPTER)] if phase == "holdout" else []):
            model.load_adapter(str(path), adapter_name=name, is_trainable=False)
        model.eval()
        model.requires_grad_(False)
        predictions = []
        for arm in arms:
            if not arm.startswith("base_"):
                model.set_adapter(arm)
            predictions.extend(run_arm(model, tokenizer, rows, arm, examples, out))
        write_json(out / "predictions.json", predictions)
        write_json(out / "summary.json", summarize(predictions, rows, arms))
    print(f"V3 {phase} evaluation COMPLETE", flush=True)


if __name__ == "__main__":
    main()
