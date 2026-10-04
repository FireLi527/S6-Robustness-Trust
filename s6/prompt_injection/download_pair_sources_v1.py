"""Download pinned public data only; never run upstream code or follow payload URLs."""
from __future__ import annotations

from pathlib import Path
import requests
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, write_json

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "secfid": {"repository": "mjhermon/SecFid", "revision": "97fa8d11a98ad197e9a87770255171c6300bfbbf", "license": "Apache-2.0",
               "files": ["README.md", "LICENSE", "metadata/release_manifest.json", "data/secfid.jsonl", "data/secfid_agentic.jsonl", "THIRD_PARTY_LICENSES/InjecAgent-LICENSE", "THIRD_PARTY_LICENSES/NOTICE.md"]},
    "aspi": {"repository": "ScaleAI/aspi", "revision": "8aaafd059a345eaf60019a6a35472c31a8527bd7", "license": "CC-BY-4.0, upstream AgentDojo MIT",
             "files": ["README.md", "LICENSE", "data/banking.jsonl", "data/slack.jsonl", "data/travel.jsonl", "data/workspace.jsonl"]},
}


def main() -> None:
    """Fetch small explicitly enumerated files into an exclusive audit snapshot."""
    out = ROOT / "external/paired_source_audit_v1"
    with new_run(out, {"sources": SOURCES, "code_sha256": file_sha256(Path(__file__)),
                       "usage": "source audit only; no auto-derived risk labels, training or scoring"}):
        manifest = {}
        for name, source in SOURCES.items():
            for filename in source["files"]:
                url = f'https://huggingface.co/datasets/{source["repository"]}/resolve/{source["revision"]}/{filename}'
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                if len(response.content) > 30_000_000:
                    raise ValueError("Unexpected file size; stop before storing")
                path = out / name / filename
                atomic_binary(path, lambda stream, data=response.content: stream.write(data))
                manifest[f"{name}/{filename}"] = {"url": url, "bytes": len(response.content), "sha256": file_sha256(path)}
                print(f"Downloaded {name}/{filename}: {len(response.content)} bytes", flush=True)
        write_json(out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
