"""Freeze fresh natural-code and external file-content confirmation samples."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from evaluate_code_external_v1 import BENCHMARK, ROOT, SEED, sha, source_sample


DATA = ROOT / "data/bipia/code_context_v2"
AIB = ROOT / "external/AgentInjectionBench"
PREVIOUS = ROOT / "data/bipia/code_external_v1/samples.jsonl"


def prepare() -> None:
    if DATA.exists():
        raise FileExistsError("Confirmation set already frozen")
    if not AIB.is_dir() or not BENCHMARK.is_dir():
        raise FileNotFoundError("External benchmark checkout missing")
    import pandas
    import scipy

    prior = {json.loads(line)["source_id"] for line in PREVIOUS.read_text(encoding="utf-8").splitlines()}
    rows = []
    for name, package in (("pandas", pandas), ("scipy", scipy)):
        root = Path(package.__file__).parent
        candidates = []
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(root)
            source_id = f"{name}/{relative.as_posix()}"
            if source_id in prior or any(part.startswith("test") or part in {"tests", "_testing"} for part in relative.parts):
                continue
            sample = source_sample(path)
            if sample:
                snippet, file_hash = sample
                candidates.append((source_id, snippet, file_hash))
        random.Random(SEED + 1).shuffle(candidates)
        if len(candidates) < 50:
            raise ValueError(f"Not enough fresh {name} files")
        for source_id, snippet, file_hash in candidates[:50]:
            rows.append({"kind": "natural_clean", "source_id": source_id,
                         "source_file_sha256": file_hash, "content": snippet})

    upstream = AIB / "data/agent_injection_bench.jsonl"
    for line in upstream.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("injection_surface") != "file_content":
            continue
        tool_results = [item for item in entry["conversation"] if item["role"] == "tool_result"]
        if len(tool_results) != 1:
            raise ValueError(f"Unexpected tool-result count: {entry['id']}")
        rows.append({"kind": "external_file_content", "source_id": entry["id"],
                     "label": entry["ground_truth"], "category": entry["attack_category"],
                     "content": tool_results[0]["content"]})
    if len(rows) != 110 or sum(r["label"] == "unsafe" for r in rows if r["kind"] == "external_file_content") != 8:
        raise ValueError("Unexpected confirmation composition")
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    protocol = {"status": "FROZEN_BEFORE_CANDIDATE_IMPLEMENTATION", "seed": SEED + 1,
                "natural_source": {"pandas": pandas.__version__, "scipy": scipy.__version__},
                "natural_files_per_package": 50,
                "external_url": "https://github.com/ppradyoth/AgentInjectionBench",
                "external_commit": (AIB / ".git/refs/heads/main").read_text(encoding="ascii").strip(),
                "external_license": "Apache-2.0",
                "external_subset": "all 10 published file_content cases; eight unsafe, two safe",
                "sample_sha256": sha(raw),
                "limitations": ["The file-content subset is only 10 cases and includes non-Python and non-comment surfaces.",
                                "The researcher inspected some source metadata before candidate implementation; not strictly blind.",
                                "Unmodified natural code is provenance-based presumptive benign, not independently annotated.",
                                "Static detector labels are not agent attack-success outcomes."]}
    DATA.mkdir(parents=True, exist_ok=False)
    (DATA / "samples.jsonl").write_bytes(raw)
    (DATA / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FROZEN {len(rows)} confirmation rows; sha256={hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    prepare()
