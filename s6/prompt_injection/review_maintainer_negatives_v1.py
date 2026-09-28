"""Prioritize frozen maintainer-document candidates for human review."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from code_workflow_signal import assess_workflow_redirection
from detector import detect_prompt_injection
from supervised_data import ROOT


DATA = ROOT / "data/bipia/maintainer_negatives_v1"
OUT = ROOT / "results/bipia/maintainer_negatives_v1"


def review_queue() -> tuple[dict, list[dict]]:
    protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
    raw = (DATA / "samples.jsonl").read_bytes()
    if protocol["status"] != "FROZEN_BEFORE_ANNOTATION" or hashlib.sha256(raw).hexdigest() != protocol["samples_sha256"]:
        raise ValueError("Frozen maintainer-document samples changed")
    samples = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    if len(samples) != protocol["count"] or len({r["source_id"] for r in samples}) != len(samples):
        raise ValueError("Unexpected maintainer sample count or duplicated source")
    rows = []
    for sample in samples:
        rule = detect_prompt_injection(sample["content"])
        workflow = assess_workflow_redirection(sample["content"])
        rows.append({"source_id": sample["source_id"], "repo": sample["repo"],
                     "path": sample["path"], "first_line": sample["first_line"],
                     "last_line": sample["last_line"],
                     "content_sha256": hashlib.sha256(sample["content"].encode("utf-8")).hexdigest(),
                     "upstream_source_status": sample["label"],
                     "p1_flagged": rule.decision != "ALLOW",
                     "workflow_flagged": workflow["decision"] != "ALLOW",
                     "review_priority": "high" if rule.decision != "ALLOW" or workflow["decision"] != "ALLOW" else "normal",
                     "reviewer_1_label": "", "reviewer_2_label": "", "adjudicated_label": ""})
    rows.sort(key=lambda row: (row["review_priority"] != "high", row["repo"], row["source_id"]))
    return protocol, rows


def write() -> None:
    if (OUT / "review_queue.csv").exists() or (OUT / "summary.json").exists():
        raise FileExistsError("Maintainer review output already exists")
    protocol, rows = review_queue()
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "review_queue.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"status": "AWAITING_INDEPENDENT_REVIEW", "samples_sha256": protocol["samples_sha256"],
               "candidate_count": len(rows), "repos": {name: sum(r["repo"] == name for r in rows)
                                                   for name in ("requests", "flask", "pytest")},
               "p1_flagged_candidates": sum(r["p1_flagged"] for r in rows),
               "workflow_flagged_candidates": sum(r["workflow_flagged"] for r in rows),
               "warning": "Flagged counts are review-priority counts, NOT false-positive rates; no independent benign labels yet."}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    write()
