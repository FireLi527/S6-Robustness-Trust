"""Frozen five-arm inference, with complete input and explicit duplicate reuse."""
from contextlib import nullcontext
from importlib.metadata import version
from pathlib import Path
import torch
from transformers import AutoTokenizer
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_scale_metrics_v1 import ARMS, jobs, summarize
from s6.prompt_injection.relation_sft_runtime import load_model
from s6.prompt_injection.relation_sft_v2_evaluation import generate
from s6.prompt_injection.relation_sft_v2_io import tokens

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "results/bipia/relation_scale_training_v1"
DATA = ROOT / "data/bipia/relation_scale_training_v1"
MODEL = ROOT / "external/qwen3_4b_train_v1"
OUT = ROOT / "results/bipia/relation_scale_evaluation_v1"


def prepare() -> tuple:
    """Bind completed models, unchanged protocol and all inference dependencies."""
    if OUT.exists():
        raise FileExistsError("Evaluation exists; never overwrite or silently resume")
    if read_json(TRAIN / "status.json")["state"] != "COMPLETE":
        raise ValueError("Training incomplete")
    parent = read_json(TRAIN / "protocol.json")
    protected = dict(parent["protected_sha256"])
    for name in ("protocol.json", "completion.json", "status.json"):
        protected[str((TRAIN / name).relative_to(ROOT))] = file_sha256(TRAIN / name)
    for arm in ARMS[2:]:
        if read_json(TRAIN / arm / "status.json")["state"] != "COMPLETE":
            raise ValueError("Adapter incomplete")
        complete = read_json(TRAIN / arm / "completion.json")
        for name, digest in complete["adapter_sha256"].items():
            protected[str((TRAIN / arm / name).relative_to(ROOT))] = digest
    for name in ("relation_scale_metrics_v1.py", "evaluate_relation_scale_v1.py", "verify_relation_scale_v1.py",
                 "relation_sft_v2_evaluation.py", "relation_sft_v2_io.py", "relation_contract_v2.py"):
        path = Path(__file__).parent / name
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    for name, digest in protected.items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    for name, digest in parent["model_files_sha256"].items():
        require_hash(MODEL / name, digest)
    rows = read_json(DATA / "samples.json")
    examples = [next(r for r in rows if r["id"] == parent["fewshot_ids"][0])]
    selected = [r for r in rows if r["split"] == "validation"]
    unique = jobs(selected)
    if len(selected) != 36 or len(unique) != 42 or examples[0]["split"] != "train":
        raise ValueError("Unexpected evaluation coverage")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    maximum = max(len(tokens(tokenizer, r, s, demos)) for r, s in unique for demos in (None, examples))
    if maximum + 1600 > 4096:
        raise ValueError("Full input budget exceeded")
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4.5 * 1024**3:
        raise RuntimeError("Insufficient GPU memory; no process eviction")
    protocol = {"protected_sha256": protected, "model_files_sha256": parent["model_files_sha256"],
                "fewshot_ids": [r["id"] for r in examples], "arms": list(ARMS), "unique_calls": 210,
                "expanded_records": 360, "max_input_tokens": maximum,
                "generation": "v2 greedy1600 new4096 total, BF16 autocast, no grammar/output repair",
                "deduplication": "Within each arm by exact side/text with identical reference. Reuse is explicit; no cross-arm cache.",
                "selection": "No retraining, thresholds or checkpoint selection. Development validation only.",
                "packages": {n: version(n) for n in ("torch", "transformers", "peft", "bitsandbytes")}}
    return protocol, tokenizer, selected, examples


def evaluate_arm(model, tokenizer, rows: list, examples: list, arm: str) -> list:
    """Generate unique inputs then expand to cases without claiming new calls."""
    if arm not in ARMS:
        raise ValueError("Unknown arm")
    if arm in ARMS[2:]:
        model.load_adapter(str(TRAIN / arm / "adapter"), adapter_name=arm, is_trainable=False)
        model.set_adapter(arm)
    model.eval()
    model.requires_grad_(False)
    demos = examples if arm == "base_fewshot" else None
    cache = {}
    for index, (row, side) in enumerate(jobs(rows), 1):
        context = model.disable_adapter() if arm.startswith("base_") else nullcontext()
        with context:
            result = generate(model, tokenizer, row, side, demos)
        call = {"id": row["id"], "side": side, "arm": arm, **result}
        write_json(OUT / "raw" / f"{arm}_{row['id']}_{side}.json", call)
        cache[(side, row["inputs"][side])] = call
        print(f"{arm}: {index}/42 {row['id']} {side}", flush=True)
    expanded = []
    for row in rows:
        for side in ("task", "content"):
            call = cache[(side, row["inputs"][side])]
            expanded.append({**call, "id": row["id"], "inference_id": call["id"]})
    write_json(OUT / f"{arm}_predictions.json", expanded)
    return expanded


def main() -> None:
    protocol, tokenizer, rows, examples = prepare()
    with new_run(OUT, protocol):
        model = load_model(MODEL)
        model.gradient_checkpointing_disable()
        model.config.use_cache = True
        predictions = []
        for arm in ARMS:
            predictions.extend(evaluate_arm(model, tokenizer, rows, examples, arm))
        write_json(OUT / "predictions.json", predictions)
        write_json(OUT / "summary.json", summarize(predictions, rows))
        for name, digest in protocol["protected_sha256"].items():
            require_hash(ROOT / name.replace("\\", "/"), digest)
    print("Five-arm development evaluation COMPLETE", flush=True)


if __name__ == "__main__":
    main()
