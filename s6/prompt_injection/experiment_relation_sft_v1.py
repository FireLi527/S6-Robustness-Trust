"""Fixed three-epoch local 4B adapter pilot; all test scoring after training."""
from pathlib import Path
from importlib.metadata import version
import torch
from transformers import AutoTokenizer
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_sft_io import FEWSHOT_IDS, training_records
from s6.prompt_injection.relation_sft_runtime import load_model, train, generate

ROOT = Path(__file__).resolve().parents[2]


def evaluate(model, tokenizer, rows: list[dict], examples: list[dict], out: Path) -> dict:
    """Unmodified quantized base vs fixed train examples vs trained adapter."""
    model.eval()
    model.gradient_checkpointing_disable()
    model.config.use_cache = True
    results = []
    for row in rows:
        for side in ("task", "content"):
            for arm in ("base_zero", "base_fewshot", "adapter_zero"):
                if arm == "adapter_zero":
                    result = generate(model, tokenizer, row, side)
                else:
                    with model.disable_adapter():
                        result = generate(model, tokenizer, row, side, examples if arm == "base_fewshot" else None)
                record = {"id": row["id"], "split": row["split"], "side": side, "arm": arm, **result}
                results.append(record)
                write_json(out / "raw" / f"{row['id']}_{side}_{arm}.json", record)
            print(f"Evaluated {row['split']} {row['id']} {side}", flush=True)
    write_json(out / "predictions.json", results)
    summary = {}
    for split in ("validation", "test"):
        summary[split] = {}
        for arm in ("base_zero", "base_fewshot", "adapter_zero"):
            group = [r for r in results if r["split"] == split and r["arm"] == arm]
            summary[split][arm] = {"side_samples": len(group), **{key: sum(r["score"][key] for r in group)
                                             for key in ("valid", "mode_correct", "actions_exact", "fields_exact")},
                                  "unfinished": sum(not r["finished"] for r in group)}
    return summary


def main() -> None:
    data = ROOT / "data/bipia/relation_sft_v1"
    model_path = ROOT / "external/qwen3_4b_train_v1"
    protected = read_json(data / "protocol.json")["protected_sha256"]
    protected[str((data / "samples.json").relative_to(ROOT))] = read_json(data / "manifest.json")["samples_sha256"]
    for name in ("relation_sft_io.py", "relation_sft_runtime.py", "experiment_relation_sft_v1.py"):
        key = "s6/prompt_injection/" + name
        protected[key] = file_sha256(ROOT / key)
    for name, digest in protected.items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    for name, digest in read_json(model_path / "files_sha256.json").items():
        require_hash(model_path / name, digest)
    rows = read_json(data / "samples.json")
    train_rows = [r for r in rows if r["split"] == "train"]
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    records = training_records(tokenizer, train_rows)
    examples = [next(r for r in train_rows if r["id"] == identifier) for identifier in FEWSHOT_IDS]
    out = ROOT / "results/bipia/relation_sft_v1"
    protocol = {"protected_sha256": protected, "model_files_sha256": read_json(model_path / "files_sha256.json"),
                "model": read_json(model_path / "protocol.json"), "data_protocol": read_json(data / "protocol.json"),
                "packages": {n: version(n) for n in ("torch", "transformers", "peft", "accelerate", "bitsandbytes")},
                "train_unique_sides": len(records), "max_training_tokens": max(len(r["input_ids"]) for r in records),
                "fewshot_train_ids": FEWSHOT_IDS, "generation": "greedy,1200 new tokens,4096 total budget,no JSON grammar forcing",
                "memory": "NF4 with double quantization, BF16 compute and frozen embeddings, nonreentrant gradient checkpointing",
                "evaluation": "No early stopping/checkpoint selection. Strict technical extraction fields, not attack recall/FPR or independent natural-source benchmark."}
    with new_run(out, protocol):
        model = load_model(model_path)
        write_json(out / "parameters.json", {"trainable": sum(p.numel() for p in model.parameters() if p.requires_grad),
                   "trainable_names": [n for n, p in model.named_parameters() if p.requires_grad], "gpu": torch.cuda.get_device_name(0)})
        trace = train(model, records, out)
        summary = evaluate(model, tokenizer, [r for r in rows if r["split"] != "train"], examples, out)
        write_json(out / "summary.json", summary)
        write_json(out / "completion.json", {"optimizer_steps": len(trace), "peak_gpu_bytes": torch.cuda.max_memory_allocated(),
                   "adapter_sha256": {str(p.relative_to(out)): file_sha256(p) for p in (out / "adapter").iterdir() if p.is_file()}})
        for name, digest in protected.items():
            require_hash(ROOT / name.replace("\\", "/"), digest)
    print("Adapter pilot COMPLETE", flush=True)


if __name__ == "__main__":
    main()
