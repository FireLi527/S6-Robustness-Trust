"""Download a pinned public classifier snapshot only; do not execute repository code."""
from pathlib import Path
import json
import urllib.request
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, write_json

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Record remote LFS hashes, local hashes, license and exact revision."""
    spec = read_json(ROOT / "data/bipia/content_probe_v1/protocol.json")["classifier"]
    repo, revision = spec['repo'], spec['revision']
    out = ROOT / "external/content_classifier_v1"
    url = f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    if metadata['sha'] != revision or metadata.get('gated'):
        raise ValueError("Snapshot identity/access mismatch")
    names = ['config.json', 'model.safetensors', 'tokenizer.json', 'tokenizer_config.json',
             'special_tokens_map.json', 'added_tokens.json', 'spm.model', 'LICENSE', 'README.md']
    upstream = {r['rfilename']: r for r in metadata['siblings']}
    with new_run(out, {"repo": repo, "revision": revision, "license": "Apache-2.0", "prompt_guard_2": "401 gated; not downloaded"}):
        hashes = {}
        for name in names:
            def download(stream, filename=name):
                link = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
                with urllib.request.urlopen(link, timeout=120) as response:
                    while block := response.read(1024*1024):
                        stream.write(block)
            atomic_binary(out / name, download)
            digest = file_sha256(out / name)
            expected = upstream[name].get('lfs', {}).get('sha256')
            if expected and expected != digest:
                raise ValueError(f"Upstream weight hash mismatch: {name}")
            hashes[name] = digest
            print(f"Downloaded {name}", flush=True)
        write_json(out / 'files_sha256.json', hashes)


if __name__ == '__main__':
    main()
