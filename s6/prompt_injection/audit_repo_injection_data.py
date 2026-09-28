"""Audit candidate repository-injection data without training or copying text."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from supervised_data import ROOT


OUT = ROOT / "results/bipia/repo_corpus_v1"
ASHWIN = ROOT / "external/prompt-injection-benchmark/dataset/v1.0.0"
AIB = ROOT / "external/AgentInjectionBench/data/agent_injection_bench.jsonl"
REPOGUARD = ROOT / "external/RepoGuardBench/data"
PRIOR = ROOT / "data/bipia/code_external_v1/samples.jsonl"
CONFIRM = ROOT / "data/bipia/code_context_v2/samples.jsonl"
INDIRECT_CHANNELS = {"tool_output", "retrieved_document", "web_content", "file_upload"}


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit() -> dict:
    required = [ASHWIN / "full.jsonl", AIB, PRIOR, CONFIRM,
                REPOGUARD / "repoguardbench_core.jsonl", REPOGUARD / "repoguardbench_real.jsonl"]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    ashwin = lines(ASHWIN / "full.jsonl")
    aib = lines(AIB)
    prior = lines(PRIOR)
    confirmation = lines(CONFIRM)
    source_hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): file_sha(path) for path in required}

    prior_clean = {r["source_id"] for r in prior if r["kind"] == "natural_clean"}
    confirm_clean = {r["source_id"] for r in confirmation if r["kind"] == "natural_clean"}
    if prior_clean & confirm_clean:
        raise ValueError("Natural code source files leaked across previous evaluation sets")
    repo_attacks = [r for r in prior if r["kind"] == "benchmark_attack"]
    repo_clean = [r for r in prior if r["kind"] == "benchmark_clean"]
    if len(repo_attacks) != 470 or len(repo_clean) != 94 or len({r["goal"] for r in repo_attacks}) != 5:
        raise ValueError("Unexpected RepoGuardBench composition")
    aib_file = [r for r in aib if r.get("injection_surface") == "file_content"]
    if len(aib_file) != 10:
        raise ValueError("Unexpected AgentInjectionBench file-content composition")
    ashwin_indirect = [r for r in ashwin if r["channel"] in INDIRECT_CHANNELS]
    ashwin_direct = [r for r in ashwin if r["channel"] not in INDIRECT_CHANNELS]
    if len(ashwin) != 82 or len(ashwin_indirect) != 17:
        raise ValueError("Unexpected prompt-injection-benchmark composition")
    upstream_hash = json.loads((ASHWIN / "metadata.json").read_text(encoding="utf-8"))["sha256_full_jsonl"]
    # The checkout uses CRLF on Windows; upstream metadata hashes LF bytes.
    normalized_ashwin_hash = hashlib.sha256((ASHWIN / "full.jsonl").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if normalized_ashwin_hash != upstream_hash:
        raise ValueError("Third-party versioned corpus hash does not match metadata")

    return {
        "status": "AUDITED_NO_TRAINING",
        "source_sha256": source_hashes,
        "source_repositories": {
            "RepoGuardBench": {"url": "https://github.com/DaoyuanLi2816/RepoGuardBench",
                               "commit": "f1c1d28d2e308e353b63458c27f4df091f5503c7", "license": "CC BY 4.0"},
            "AgentInjectionBench": {"url": "https://github.com/ppradyoth/AgentInjectionBench",
                                    "commit": "5adb09800170683793b4e4d015e42e2002fa5adf", "license": "Apache-2.0"},
            "prompt-injection-benchmark": {"url": "https://github.com/AshwinNHacker/prompt-injection-benchmark",
                                            "commit": "3e001b3dc898fdfc2f725ddc8b77258c9936e07c", "license": "MIT"}},
        "source_inventory": {
            "repoguard_code_comment": {"attack_rows": len(repo_attacks), "attack_goal_templates": len({r["goal"] for r in repo_attacks}),
                                       "repository_tasks": len({r["source_id"] for r in repo_attacks}),
                                       "clean_rows": len(repo_clean), "origin": "author-written synthetic micro-repositories",
                                       "status": "development_exposed; not an independent test"},
            "aib_file_content": {"unsafe_rows": sum(r["ground_truth"] == "unsafe" for r in aib_file),
                                 "safe_rows": sum(r["ground_truth"] == "safe" for r in aib_file),
                                 "carriers": "mixed Python, README, JSON, JavaScript, notebook",
                                 "status": "confirmation_exposed; no longer a fresh holdout"},
            "ashwin_indirect": {"injection_rows": sum(r["label"] == "injection" for r in ashwin_indirect),
                                "benign_rows": sum(r["label"] == "benign" for r in ashwin_indirect),
                                "channels": dict(Counter(r["channel"] for r in ashwin_indirect)),
                                "status": "new adjacent-domain candidate; not repository-specific"},
            "ashwin_direct_excluded": {"rows": len(ashwin_direct),
                                       "reason": "direct user input is a different trust boundary"},
            "natural_python_code": {"prior_files": len(prior_clean), "confirmation_files": len(confirm_clean),
                                    "file_overlap": len(prior_clean & confirm_clean),
                                    "status": "unmodified-source presumed benign, not independently adjudicated"}},
        "training_readiness": {
            "decision": "NOT_READY",
            "reasons": ["Only five repeated RepoGuardBench attack templates in the core repository-specific development source.",
                        "The eight external file-content attacks were already used for confirmation and cannot be presented as a new blind test.",
                        "The new third-party indirect samples are adjacent-domain, not a repository-file corpus.",
                        "Natural-source benign labels and legitimate maintainer hard negatives lack independent adjudication."],
            "next_data_requirements": ["Acquire additional repository-artifact attacks from distinct sources and record the exact controlled text span and requested deviation.",
                                       "Collect normal maintainer instructions with similar action/authority vocabulary, then adjudicate them separately from provenance-based code snippets.",
                                       "Freeze a source- and attack-family-disjoint external test set before fitting or choosing a threshold."]}}


def candidate_manifest() -> list[dict]:
    """One row per attack family or external case; no sample text is exported."""
    prior = lines(PRIOR)
    confirmation = lines(CONFIRM)
    ashwin = lines(ASHWIN / "full.jsonl")
    rows = []
    for goal in sorted({r["goal"] for r in prior if r["kind"] == "benchmark_attack"}):
        example = next(r for r in prior if r["kind"] == "benchmark_attack" and r["goal"] == goal)
        rows.append({"source": "RepoGuardBench", "unit_id": goal, "carrier": "python_code_comment",
                     "upstream_label": "attack", "text_sha256": hashlib.sha256(example["content"].encode()).hexdigest(),
                     "prior_exposure": "development", "scope": "repository_specific",
                     "review_status": "upstream_label_only"})
    for item in confirmation:
        if item["kind"] != "external_file_content":
            continue
        rows.append({"source": "AgentInjectionBench", "unit_id": item["source_id"],
                     "carrier": "mixed_file_content", "upstream_label": item["label"],
                     "text_sha256": hashlib.sha256(item["content"].encode()).hexdigest(),
                     "prior_exposure": "confirmation", "scope": "mixed_repository_adjacent",
                     "review_status": "upstream_label_only"})
    for item in ashwin:
        if item["channel"] not in INDIRECT_CHANNELS:
            continue
        rows.append({"source": "prompt-injection-benchmark", "unit_id": item["id"],
                     "carrier": item["channel"], "upstream_label": item["label"],
                     "text_sha256": hashlib.sha256(item["text"].encode()).hexdigest(),
                     "prior_exposure": "not_scored_in_this_project", "scope": "adjacent_indirect_not_repository_specific",
                     "review_status": "upstream_label_only"})
    if len(rows) != 32 or len({(r["source"], r["unit_id"]) for r in rows}) != 32:
        raise ValueError("Candidate family/case manifest is incomplete or duplicated")
    return rows


def write() -> None:
    if OUT.exists():
        raise FileExistsError("Data audit already exists; do not overwrite")
    result = audit()
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / "source_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manifest()
    print(json.dumps(result["source_inventory"], ensure_ascii=False, indent=2))


def write_manifest() -> None:
    path = OUT / "candidate_manifest.csv"
    if not OUT.is_dir() or path.exists():
        raise FileExistsError("Audit directory missing or candidate manifest already exists")
    with path.open("w", newline="", encoding="utf-8") as handle:
        rows = candidate_manifest()
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} unique candidate families/cases")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("audit", "manifest"), nargs="?", default="audit")
    args = parser.parse_args()
    write() if args.mode == "audit" else write_manifest()
