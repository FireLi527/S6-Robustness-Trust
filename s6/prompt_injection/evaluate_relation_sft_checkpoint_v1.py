"""Resume evaluation only after mixed-precision generation failure; never retrain."""
from pathlib import Path
import torch
from transformers import AutoTokenizer
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.relation_sft_io import FEWSHOT_IDS
from s6.prompt_injection.relation_sft_runtime import load_model, generate

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "results/bipia/relation_sft_v1"


def evaluate(model, tokenizer, rows: list[dict], examples: list[dict], out: Path) -> dict:
    """Same frozen generation settings, with BF16 autocast matching training."""
    model.eval()
    model.gradient_checkpointing_disable()
    model.config.use_cache = True
    results = []
    for row in rows:
        for side in ("task", "content"):
            for arm in ("base_zero", "base_fewshot", "adapter_zero"):
                with torch.autocast("cuda", dtype=torch.bfloat16):
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
    old = read_json(TRAIN / "protocol.json")
    trace = read_json(TRAIN / "training_trace.json")
    if len(trace) != 21 or {r["epoch"] for r in trace} != {1, 2, 3}:
        raise ValueError("Expected completed fixed three-epoch training")
    if list((TRAIN / "raw").glob("*.json")):
        raise ValueError("Prior predictions exist; do not overwrite/reselect")
    protected = {**old["protected_sha256"],
                 **{str(p.relative_to(ROOT)): file_sha256(p) for p in TRAIN.rglob("*") if p.is_file()},
                 str(Path(__file__).relative_to(ROOT)): file_sha256(Path(__file__))}
    for name, digest in protected.items():
        require_hash(ROOT / name.replace("\\", "/"), digest)
    path = ROOT / "external/qwen3_4b_train_v1"
    for name, digest in old["model_files_sha256"].items():
        require_hash(path / name, digest)
    rows = read_json(ROOT / "data/bipia/relation_sft_v1/samples.json")
    examples = [next(r for r in rows if r["id"] == identifier and r["split"] == "train") for identifier in FEWSHOT_IDS]
    out = ROOT / "results/bipia/relation_sft_v1_evaluation"
    adapter_hashes = {str(p.relative_to(TRAIN)): file_sha256(p) for p in (TRAIN / "adapter").iterdir() if p.is_file()}
    with new_run(out, {"protected_sha256": protected, "source_training": str(TRAIN.relative_to(ROOT)),
                       "original_status": read_json(TRAIN / "status.json"), "change": "Add BF16 autocast during generation; no retraining or parameter/data changes",
                       "adapter_sha256": adapter_hashes, "original_protocol": old}):
        tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
        model = load_model(path)
        model.load_adapter(str(TRAIN / "adapter"), adapter_name="trained", is_trainable=False)
        model.set_adapter("trained")
        summary = evaluate(model, tokenizer, [r for r in rows if r["split"] != "train"], examples, out)
        write_json(out / "summary.json", summary)
        write_json(out / "completion.json", {"optimizer_steps": len(trace), "adapter_sha256": adapter_hashes,
                   "peak_evaluation_gpu_bytes": torch.cuda.max_memory_allocated(), "retrained": False})
        for name, digest in protected.items():
            require_hash(ROOT / name.replace("\\", "/"), digest)
    print("Checkpoint evaluation COMPLETE", flush=True)


if __name__ == "__main__":
    main()
