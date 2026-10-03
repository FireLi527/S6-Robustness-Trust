"""Fresh LoRA training on v3 references; arms fixed before training, no evaluation or selection."""
import argparse
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/relation_scale_training_v3"
MODEL = ROOT / "external/qwen3_4b_train_v1"
OUT = ROOT / "results/bipia/relation_scale_training_v3"
ARMS = ("small_8", "medium_16", "large_28")


def protected_files() -> dict:
    protected = dict(read_json(DATA / "protocol.json")["protected_sha256"])
    for name in ("protocol.json", "manifest.json", "samples.json"):
        protected[str((DATA / name).relative_to(ROOT)).replace("\\", "/")] = file_sha256(DATA / name)
    require_hash(DATA / "samples.json", read_json(DATA / "manifest.json")["samples_sha256"])
    protected["s6/prompt_injection/experiment_relation_scale_training_v3.py"] = file_sha256(Path(__file__))
    for key, digest in protected.items():
        require_hash(ROOT / key, digest)
    return protected


def preflight(arms: list) -> dict:
    """Budgets for every chosen arm and all validation prompts, before any gradient step."""
    import torch
    from transformers import AutoTokenizer
    from s6.prompt_injection.relation_sft_v3_io import records, tokens
    if read_json(DATA / "status.json")["state"] != "COMPLETE":
        raise ValueError("v3 data not frozen")
    protected = protected_files()
    hashes = read_json(MODEL / "files_sha256.json")
    for name, digest in hashes.items():
        require_hash(MODEL / name, digest)
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    rows = read_json(DATA / "samples.json")
    examples = [next(r for r in rows if r["id"] == "scale-seed-dev2-01")]
    subsets = read_json(DATA / "protocol.json")["subsets"]
    sizes = {}
    for arm in arms:
        prepared = records(tokenizer, [r for r in rows if r["split"] == "train" and r["group_id"] in subsets[arm]])
        sizes[arm] = {"unique_sides": len(prepared), "max_tokens": max(len(r["input_ids"]) for r in prepared),
                      "optimizer_steps": 3 * ((len(prepared) + 3) // 4)}
    maximum = max(len(tokens(tokenizer, r, s, examples)) for r in rows if r["split"] == "validation" for s in ("task", "content"))
    if maximum + 1600 > 4096:
        raise ValueError("Validation full-text budget exceeded")
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4.5 * 1024**3:
        raise RuntimeError("Need at least 4.5 GiB free GPU; no user process eviction")
    return {"protected_sha256": protected, "model_files_sha256": hashes, "arms": arms, "sizes": sizes,
            "max_validation_prompt_tokens": maximum, "fewshot_ids": [examples[0]["id"]],
            "packages": {n: version(n) for n in ("torch", "transformers", "peft", "bitsandbytes")},
            "evaluation_status": "Not started; holdout sealed"}


def train_arm(arm: str) -> None:
    """Fresh base and optimizer per subprocess; reuses the frozen public NF4 LoRA runtime."""
    import torch
    from transformers import AutoTokenizer
    from s6.prompt_injection.relation_sft_runtime import load_model, train
    from s6.prompt_injection.relation_sft_v3_io import records
    if read_json(OUT / "status.json")["state"] != "RUNNING":
        raise ValueError("Batch parent is not running")
    protocol = read_json(OUT / "protocol.json")
    if arm not in protocol["arms"]:
        raise ValueError("Arm not registered before training")
    for key, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / key, digest)
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4.5 * 1024**3:
        raise RuntimeError("Insufficient free GPU at arm start")
    groups = read_json(DATA / "protocol.json")["subsets"][arm]
    rows = [r for r in read_json(DATA / "samples.json") if r["split"] == "train" and r["group_id"] in groups]
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    prepared = records(tokenizer, rows)
    out = OUT / arm
    with new_run(out, {"arm": arm, "parent_protocol_sha256": file_sha256(OUT / "protocol.json"), "groups": groups,
                       "training": protocol["sizes"][arm], "evaluation": "Not started"}):
        model = load_model(MODEL)
        trace = train(model, prepared, out)
        if len(trace) != protocol["sizes"][arm]["optimizer_steps"]:
            raise ValueError("Optimizer step mismatch")
        write_json(out / "completion.json", {"steps": len(trace), "peak_gpu_bytes": torch.cuda.max_memory_allocated(),
                   "adapter_sha256": {str(p.relative_to(out)).replace("\\", "/"): file_sha256(p)
                                      for p in (out / "adapter").iterdir() if p.is_file()}})
    print(f"V3 arm {arm} COMPLETE", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, help="internal: one subprocess arm")
    parser.add_argument("--arms", help="comma-separated arms to register and train, e.g. large_28")
    args = parser.parse_args()
    if args.arm:
        train_arm(args.arm)
        return
    arms = [a for a in ARMS if a in (args.arms or "").split(",")]
    if not arms or len(arms) != len((args.arms or "").split(",")):
        raise ValueError("Specify --arms from small_8,medium_16,large_28")
    if OUT.exists():
        raise FileExistsError("V3 training run exists; never overwrite or silently resume")
    protocol = preflight(arms)
    with new_run(OUT, protocol):
        for arm in arms:
            print(f"Starting v3 arm {arm}", flush=True)
            subprocess.run([sys.executable, "-u", "-m", "s6.prompt_injection.experiment_relation_scale_training_v3",
                            "--arm", arm], check=True)
        for key, digest in protocol["protected_sha256"].items():
            require_hash(ROOT / key, digest)
        write_json(OUT / "completion.json", {"arms": {a: read_json(OUT / a / "completion.json") for a in arms},
                   "evaluation_started": False})
    print("V3 training COMPLETE; evaluation not yet run", flush=True)


if __name__ == "__main__":
    main()
