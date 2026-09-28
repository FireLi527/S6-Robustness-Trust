"""Develop on RepoGuardBench and confirm on frozen new-source file content."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from code_context_signal import assess_comment_redirection
from code_workflow_signal import assess_workflow_redirection
from detector import detect_prompt_injection
from evaluate_code_external_v1 import DATA as DEVELOPMENT, ROOT, sha


CONFIRMATION = ROOT / "data/bipia/code_context_v2"
RESULTS = ROOT / "results/bipia/code_context_v2"
SIGNAL = Path(__file__).with_name("code_workflow_signal.py")


def load_rows(folder: Path, expected_status: str) -> tuple[dict, list[dict]]:
    protocol = json.loads((folder / "protocol.json").read_text(encoding="utf-8"))
    raw = (folder / "samples.jsonl").read_bytes()
    hash_key = "sample_sha256"
    if protocol["status"] != expected_status or sha(raw) != protocol[hash_key]:
        raise ValueError(f"Frozen sample mismatch: {folder}")
    return protocol, [json.loads(line) for line in raw.decode("utf-8").splitlines()]


def predict(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        text = row["content"]
        rule = detect_prompt_injection(text).decision != "ALLOW"
        old = assess_comment_redirection(text)["decision"] != "ALLOW"
        new = assess_workflow_redirection(text)["decision"] != "ALLOW"
        output.append({"kind": row["kind"], "source_id": row["source_id"],
                       "label": row.get("label", ""), "goal": row.get("goal", ""),
                       "rule": rule, "old_comment": old, "workflow": new,
                       "rule_or_workflow": rule or new})
    return output


def metrics(rows: list[dict]) -> dict:
    return {name: {"flagged": sum(row[name] for row in rows), "total": len(rows),
                   "rate": sum(row[name] for row in rows) / len(rows) if rows else None}
            for name in ("rule", "old_comment", "workflow", "rule_or_workflow")}


def groups(rows: list[dict]) -> dict:
    kinds = sorted({row["kind"] for row in rows})
    result = {kind: metrics([row for row in rows if row["kind"] == kind]) for kind in kinds}
    if any(row["kind"] == "external_file_content" for row in rows):
        result["external_unsafe"] = metrics([r for r in rows if r["label"] == "unsafe"])
        result["external_safe"] = metrics([r for r in rows if r["label"] == "safe"])
    return result


def save_predictions(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def development() -> None:
    if RESULTS.exists():
        raise FileExistsError("Development selection already exists")
    dev_protocol, rows = load_rows(DEVELOPMENT, "FROZEN_BEFORE_SCORING")
    confirm_protocol, _ = load_rows(CONFIRMATION, "FROZEN_BEFORE_CANDIDATE_IMPLEMENTATION")
    predictions = predict(rows)
    selection = {"status": "FROZEN_BEFORE_CONFIRMATION", "candidate": "P1 OR multi-line workflow signal",
                 "signal_sha256": sha(SIGNAL.read_bytes()),
                 "development_sample_sha256": dev_protocol["sample_sha256"],
                 "confirmation_sample_sha256": confirm_protocol["sample_sha256"],
                 "development_metrics": groups(predictions),
                 "decision": "Research-only candidate; report all confirmation results even if weak; do not deploy or tune on confirmation"}
    RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    save_predictions(RESULTS / "development_predictions.csv", predictions)
    print(json.dumps(selection["development_metrics"], ensure_ascii=False, indent=2))


def confirm() -> None:
    if (RESULTS / "summary.json").exists():
        raise FileExistsError("Confirmation already scored")
    selection = json.loads((RESULTS / "selection.json").read_text(encoding="utf-8"))
    protocol, rows = load_rows(CONFIRMATION, "FROZEN_BEFORE_CANDIDATE_IMPLEMENTATION")
    if selection["status"] != "FROZEN_BEFORE_CONFIRMATION" or selection["confirmation_sample_sha256"] != protocol["sample_sha256"]:
        raise ValueError("Confirmation set differs from selected version")
    if sha(SIGNAL.read_bytes()) != selection["signal_sha256"]:
        raise ValueError("Candidate signal changed since development")
    predictions = predict(rows)
    summary = {"status": "COMPLETE", "signal_sha256": selection["signal_sha256"],
               "confirmation_sample_sha256": protocol["sample_sha256"],
               "development_metrics": selection["development_metrics"],
               "confirmation_metrics": groups(predictions), "limitations": protocol["limitations"]}
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    save_predictions(RESULTS / "confirmation_predictions.csv", predictions)
    print(json.dumps(summary["confirmation_metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("development", "confirm"))
    args = parser.parse_args()
    development() if args.mode == "development" else confirm()
