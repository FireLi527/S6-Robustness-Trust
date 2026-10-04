"""Pinned public SecOPD snapshot for local noncommercial course research."""
from pathlib import Path
import requests
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, write_json

ROOT = Path(__file__).resolve().parents[2]
REPO = "Sizhe-Chen/Qwen3.8-27B-Thinking-SecOPD-trainset"
REVISION = "9ff5e25093995041997ea984c68a51f2b998d435"
DATA_FILE = "preference_Qwen3.8-27B_dpo_NaiveCompletion_randpos_synthetic_alpaca_optimized_thinking_xhigh_openrouter.json"


def download(url: str, path: Path, limit: int = 400_000_000) -> None:
    """Stream a bounded HTTPS download atomically; never execute downloaded text."""
    if not url.startswith("https://huggingface.co/datasets/") or limit < 1:
        raise ValueError("Unexpected source or byte limit")
    with requests.get(url, stream=True, timeout=(20, 60)) as response:
        response.raise_for_status()
        def write(stream):
            total = 0
            for block in response.iter_content(1024 * 1024):
                total += len(block)
                if total > limit:
                    raise ValueError("Source exceeds declared byte limit")
                stream.write(block)
        atomic_binary(path, write)


def main() -> None:
    out = ROOT / "external/secopd_source_v1"
    notice = {"repository": REPO, "revision": REVISION,
              "scope": "User-confirmed noncommercial graduate course research; local use only, no source redistribution",
              "license_notice": "Publisher declares no standalone dataset license; upstream terms differ. Attribution is not a license grant. No commercial or redistribution authorization is inferred.",
              "model_inputs": "trusted task and clean/injected data only; bundled chosen/rejected completions are never model features or targets",
              "code_sha256": file_sha256(Path(__file__))}
    with new_run(out, notice):
        manifest = {}
        for filename in ("README.md", "release_stats.json", "generation_config.json", "skipped_indices.json", DATA_FILE):
            url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{filename}"
            path = out / filename
            download(url, path)
            manifest[filename] = {"url": url, "sha256": file_sha256(path), "bytes": path.stat().st_size}
            print(f"Downloaded {filename}: {path.stat().st_size} bytes", flush=True)
        write_json(out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
