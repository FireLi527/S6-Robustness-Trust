"""Download official immutable 4B weights for an isolated local training pilot."""
import os
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, write_json

ROOT = Path(__file__).resolve().parents[2]
MODEL = "Qwen/Qwen3-4B"
REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"


def main() -> None:
    os.environ["HF_HOME"] = str(ROOT / "external/hf_training_download_cache")
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import HfApi, snapshot_download
    info = HfApi().model_info(MODEL, revision=REVISION, files_metadata=True, token=False)
    if info.sha != REVISION or info.card_data.get("license") != "apache-2.0":
        raise ValueError("Model revision/license differs")
    names = [f.rfilename for f in info.siblings if f.rfilename.endswith((".json", ".safetensors", ".txt", ".jinja")) or f.rfilename in ("LICENSE", "README.md")]
    sizes = {f.rfilename: f.size for f in info.siblings if f.rfilename in names}
    out = ROOT / "external/qwen3_4b_train_v1"
    with new_run(out, {"model": MODEL, "revision": REVISION, "license": "apache-2.0", "expected_sizes": sizes,
                       "code_sha256": file_sha256(Path(__file__)), "purpose": "Official HF safetensors for local adapter pilot; not Ollama GGUF training"}):
        snapshot_download(MODEL, revision=REVISION, local_dir=str(out), allow_patterns=names, token=False, max_workers=3)
        for name, size in sizes.items():
            if size is not None and (out / name).stat().st_size != size:
                raise ValueError(f"Downloaded size mismatch: {name}")
        write_json(out / "files_sha256.json", {name: file_sha256(out / name) for name in names})
    print(f"Official model ready: {out}", flush=True)


if __name__ == "__main__":
    main()
