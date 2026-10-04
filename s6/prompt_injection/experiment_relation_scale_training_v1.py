"""Sequential fresh LoRA scale training; no evaluation or checkpoint selection."""
import argparse
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/relation_scale_training_v1"
MODEL = ROOT / "external/qwen3_4b_train_v1"
OUT = ROOT / "results/bipia/relation_scale_training_v1"
ARMS = ("small_8", "medium_16", "large_28")


def protected_files() -> dict:
    """Bind both reused frozen runtime and all new conversion/protocol sources."""
    protected = read_json(DATA / "protocol.json")["protected_sha256"]
    for name in ("protocol.json", "manifest.json", "samples.json", "split_audit.json"):
        path = DATA / name
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    require_hash(DATA / "samples.json", read_json(DATA / "manifest.json")["samples_sha256"])
    for name in ("relation_sft_runtime.py", "relation_sft_io.py", "relation_contract_v1.py",
                 "relation_sft_v2_io.py", "experiment_relation_scale_training_v1.py"):
        key = "s6/prompt_injection/" + name
        protected[key] = file_sha256(ROOT / key)
    for key, digest in protected.items():
        require_hash(ROOT / key.replace("\\", "/"), digest)
    return protected


def preflight() -> dict:
    """All scales and complete validation inputs checked before any gradient step."""
    import torch
    from transformers import AutoTokenizer
    from s6.prompt_injection.relation_sft_v2_io import records, tokens
    protected = protected_files()
    hashes = read_json(MODEL / "files_sha256.json")
    for name, digest in hashes.items():
        require_hash(MODEL / name, digest)
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    rows = read_json(DATA / "samples.json")
    examples = [next(r for r in rows if r["id"] == "scale-seed-dev2-01")]
    subsets = read_json(DATA / "protocol.json")["subsets"]
    sizes = {}
    for arm, groups in subsets.items():
        selected = [r for r in rows if r["split"] == "train" and r["group_id"] in groups]
        prepared = records(tokenizer, selected)
        sizes[arm] = {"pairs": len(selected), "unique_sides": len(prepared),
                      "max_tokens": max(len(r["input_ids"]) for r in prepared),
                      "answer_tokens_per_epoch": sum(sum(v != -100 for v in r["labels"]) for r in prepared),
                      "optimizer_steps": 3 * ((len(prepared) + 3) // 4)}
    maximum = max(len(tokens(tokenizer, r, side, examples)) for r in rows if r["split"] == "validation" for side in ("task", "content"))
    if maximum + 1600 > 4096:
        raise ValueError("Validation full-text budget exceeded")
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4.5 * 1024**3:
        raise RuntimeError("Need at least4.5 GiB free GPU; no user process eviction")
    return {"protected_sha256": protected, "model_files_sha256": hashes, "sizes": sizes,
            "max_validation_prompt_tokens": maximum, "fewshot_ids": [examples[0]["id"]],
            "packages": {n: version(n) for n in ("torch", "transformers", "peft", "bitsandbytes")},
            "scope": "Three fixed training sizes, same seed/epochs/hyperparameters. Development only; no new test authored or evaluated.",
            "evaluation_status": "Not started; no inference-driven selection during training"}


def train_arm(arm: str) -> None:
    """Each subprocess has a fresh base and optimizer; never reuses another adapter."""
    import torch
    from transformers import AutoTokenizer
    from s6.prompt_injection.relation_sft_v2_io import records
    from s6.prompt_injection.relation_sft_runtime import load_model, train
    if read_json(OUT / "status.json")["state"] != "RUNNING":
        raise ValueError("Batch parent is not running")
    protocol = read_json(OUT / "protocol.json")
    for key, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / key.replace("\\", "/"), digest)
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4.5 * 1024**3:
        raise RuntimeError("Insufficient free GPU at arm start")
    groups = read_json(DATA / "protocol.json")["subsets"][arm]
    rows = [r for r in read_json(DATA / "samples.json") if r["split"] == "train" and r["group_id"] in groups]
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    prepared = records(tokenizer, rows)
    out = OUT / arm
    with new_run(out, {"arm": arm, "parent_protocol_sha256": file_sha256(OUT / "protocol.json"),
                       "groups": groups, "training": protocol["sizes"][arm], "evaluation": "Not started"}):
        model = load_model(MODEL)
        write_json(out / "parameters.json", {"trainable": sum(p.numel() for p in model.parameters() if p.requires_grad),
                   "trainable_names": [n for n, p in model.named_parameters() if p.requires_grad]})
        trace = train(model, prepared, out)
        if len(trace) != protocol["sizes"][arm]["optimizer_steps"]:
            raise ValueError("Optimizer step mismatch")
        write_json(out / "completion.json", {"steps": len(trace), "peak_gpu_bytes": torch.cuda.max_memory_allocated(),
                   "adapter_sha256": {str(p.relative_to(out)): file_sha256(p) for p in (out / "adapter").iterdir() if p.is_file()}})
    print(f"Scale arm {arm} COMPLETE", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.arm:
        train_arm(args.arm)
        return
    if OUT.exists():
        raise FileExistsError("Scale run exists; never overwrite or silently resume")
    protocol = preflight()
    with new_run(OUT, protocol):
        for arm in ARMS:
            print(f"Starting scale arm {arm}", flush=True)
            subprocess.run([sys.executable, "-u", "-m", "s6.prompt_injection.experiment_relation_scale_training_v1", "--arm", arm], check=True)
        for key, digest in protocol["protected_sha256"].items():
            require_hash(ROOT / key.replace("\\", "/"), digest)
        write_json(OUT / "completion.json", {"arms": {arm: read_json(OUT / arm / "completion.json") for arm in ARMS},
                   "evaluation_started": False, "independent_test_claim": False})
    print("All scale training arms COMPLETE; evaluation not yet run", flush=True)


if __name__ == "__main__":
    main()
