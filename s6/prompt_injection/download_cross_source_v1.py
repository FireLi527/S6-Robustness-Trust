"""Download pinned, public cross-source research data; never execute remote code."""
from pathlib import Path
from urllib.parse import urlparse
import requests
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, write_json

SOURCES = {
    "spml": ("https://huggingface.co/datasets/reshabhs/SPML_Chatbot_Prompt_Injection/resolve/02ce8084e979bc7d4c24ee35d22ecb7f2db96ff5/",
             ["README.md", "spml_prompt_injection.csv"], "MIT card; authors caution against assuming contextual generalization from training"),
    "injecagent": ("https://raw.githubusercontent.com/uiuc-kang-lab/InjecAgent/f19c9f2c79a41046eb13c03c51a24c567a8ffa07/",
                   ["README.md", "LICENCE", "data/user_cases.jsonl", "data/test_cases_dh_base.json", "data/test_cases_ds_base.json"], "MIT; evaluation only"),
    "notinject": ("https://huggingface.co/datasets/leolee99/NotInject/resolve/847ae76cf8fea5ed325429e569ae8cfef022d2e0/",
                  ["README.md", "data/NotInject_one-00000-of-00001.parquet", "data/NotInject_two-00000-of-00001.parquet", "data/NotInject_three-00000-of-00001.parquet"], "MIT card; benign-only evaluation, no invented task")}


def download(url: str, path: Path, limit: int = 150_000_000) -> None:
    """Bound individual data downloads and atomically publish complete bytes."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"huggingface.co", "raw.githubusercontent.com"} or limit < 1:
        raise ValueError("Unexpected source URL or byte budget")
    with requests.get(url, stream=True, timeout=(20, 60)) as response:
        response.raise_for_status()
        def write(stream):
            total = 0
            for block in response.iter_content(1024 * 1024):
                total += len(block)
                if total > limit:
                    raise ValueError("Data file exceeds declared limit")
                stream.write(block)
        atomic_binary(path, write)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root / "external/cross_source_v1"
    protocol = {"sources": SOURCES, "scope": "noncommercial course research; local use, no raw redistribution",
                "security": "Downloaded data are untrusted inert text; no payload execution or external service calls",
                "code_sha256": file_sha256(Path(__file__))}
    with new_run(out, protocol):
        manifest = {}
        for source, (base, files, _) in SOURCES.items():
            for filename in files:
                path = out / source / filename
                download(base + filename, path)
                manifest[f"{source}/{filename}"] = {"url": base + filename, "sha256": file_sha256(path), "bytes": path.stat().st_size}
                print(f"Downloaded {source}/{filename}: {path.stat().st_size} bytes", flush=True)
        write_json(out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
