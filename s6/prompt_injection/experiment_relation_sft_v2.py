"""Fixed v2 development pilot; new adapter, not a continuation of v1 weights."""
from pathlib import Path
from importlib.metadata import version
import torch
from transformers import AutoTokenizer
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_sft_runtime import load_model, train
from s6.prompt_injection.relation_sft_v2_io import records, tokens
from s6.prompt_injection.relation_sft_v2_evaluation import evaluate

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    data, model_path = ROOT / "data/bipia/relation_sft_v2", ROOT / "external/qwen3_4b_train_v1"
    protected = read_json(data / "protocol.json")["protected_sha256"]
    protected[str((data / "samples.json").relative_to(ROOT))] = read_json(data / "manifest.json")["samples_sha256"]
    for name in ("relation_sft_runtime.py", "relation_sft_io.py", "relation_contract_v1.py",
                 "relation_sft_v2_io.py", "relation_sft_v2_evaluation.py", "experiment_relation_sft_v2.py"):
        key = "s6/prompt_injection/" + name
        protected[key] = file_sha256(ROOT / key)
    for name, digest in protected.items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    model_hashes = read_json(model_path / "files_sha256.json")
    for name, digest in model_hashes.items():
        require_hash(model_path / name, digest)
    rows = read_json(data / "samples.json")
    training, validation = [r for r in rows if r["split"] == "train"], [r for r in rows if r["split"] == "validation"]
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    train_records = records(tokenizer, training)
    examples = [training[0]]  # Fixed first training row, chosen without evaluation.
    maximum = max(len(tokens(tokenizer, r, side, examples)) for r in validation for side in ("task", "content"))
    if maximum + 1600 > 4096:
        raise ValueError("Few-shot input/output budget exceeded before training")
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4.5 * 1024**3:
        raise RuntimeError("Insufficient free GPU memory; no eviction of user processes")
    out = ROOT / "results/bipia/relation_sft_v2"
    with new_run(out, {"protected_sha256": protected, "model_files_sha256": model_hashes,
                       "packages": {n: version(n) for n in ("torch", "transformers", "peft", "bitsandbytes")},
                       "data_protocol": read_json(data / "protocol.json"), "fewshot_ids": [r["id"] for r in examples],
                       "train_unique_sides": len(train_records), "max_training_tokens": max(len(r["input_ids"]) for r in train_records),
                       "max_fewshot_input_tokens": maximum, "generation": "greedy,1600 new,4096 total,no grammar,no output repair",
                       "evaluation": "Development validation only, fixed3 epochs; no checkpoint selection; no independent test or detection metrics"}):
        model = load_model(model_path)
        write_json(out / "parameters.json", {"trainable": sum(p.numel() for p in model.parameters() if p.requires_grad),
                   "trainable_names": [n for n, p in model.named_parameters() if p.requires_grad]})
        trace = train(model, train_records, out)
        write_json(out / "training_complete.json", {"steps": len(trace), "adapter_sha256": {
                   str(p.relative_to(out)): file_sha256(p) for p in (out / "adapter").iterdir() if p.is_file()}})
        write_json(out / "summary.json", evaluate(model, tokenizer, validation, examples, out))
        for name, digest in protected.items():
            require_hash(ROOT / name.replace("\\", "/"), digest)
    print("V2 development pilot COMPLETE", flush=True)


if __name__ == "__main__":
    main()
