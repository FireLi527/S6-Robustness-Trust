"""Pinned Apache-2.0 NLI weights for an offline authorization-method pilot."""
from pathlib import Path
import requests
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, write_json

REPO = "cross-encoder/nli-deberta-v3-small"
REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
FILES = ("README.md", "config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
         "special_tokens_map.json", "added_tokens.json", "spm.model")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    out = root / "external/nli_authorization_v1"
    with new_run(out, {"repository": REPO, "revision": REVISION, "license": "Apache-2.0 model card",
                       "purpose": "local frozen NLI method screening, no remote code or payload execution",
                       "code_sha256": file_sha256(Path(__file__))}):
        manifest = {}
        for filename in FILES:
            url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{filename}"
            with requests.get(url, stream=True, timeout=(20, 60)) as response:
                response.raise_for_status()
                def write(stream):
                    size = 0
                    for block in response.iter_content(1024 * 1024):
                        size += len(block)
                        if size > 700_000_000:
                            raise ValueError("File exceeds fixed download budget")
                        stream.write(block)
                atomic_binary(out / filename, write)
            manifest[filename] = {"url": url, "sha256": file_sha256(out / filename), "bytes": (out / filename).stat().st_size}
            print(f"Downloaded {filename}: {manifest[filename]['bytes']} bytes", flush=True)
        write_json(out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
