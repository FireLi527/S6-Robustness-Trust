"""Join explicit class/field approvals without inventing machine-level gold slots."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]


def assemble(rows: list[dict], proposals: list[dict], review: dict, confirmation: dict) -> list[dict]:
    """Export only approved text fields; preserve splits and unknown decisions."""
    ids = [r["id"] for r in rows]
    approved = confirmation["approved_ids"]
    labels = [(identifier, label) for label, values in review["human_decisions"].items() for identifier in values]
    if ids != list(range(1, 25)) or sorted(approved) != ids or sorted(i for i, _ in labels) != ids:
        raise ValueError("Approval IDs missing, duplicated or inconsistent")
    if [p["id"] for p in proposals] != ids or set(confirmation["approved_fields"]) != {"task_scope", "content_actions"}:
        raise ValueError("Proposal order or approved fields differ")
    if confirmation["human_review_status"] != "COMPLETE_FOR_CLASS_AND_TWO_TEXT_FIELDS":
        raise ValueError("Field approval incomplete")
    if any(label not in ("NORMAL", "RISK", "UNKNOWN") for _, label in labels):
        raise ValueError("Unknown classification value")
    decisions = dict(labels)
    return [{**row, "human_decision": decisions[row["id"]],
             "approved_task_scope": proposal["task_scope"], "approved_content_actions": proposal["content_actions"],
             "human_text_review_complete": True, "machine_target_status": "NOT_CONVERTED",
             "ready_for_sft": False, "tool_authorization": "not_granted"}
            for row, proposal in zip(rows, proposals, strict=True)]


def main() -> None:
    confirmation_path = ROOT / "data/bipia/repository_scope_human_review_v1/field_confirmation.json"
    confirmation = read_json(confirmation_path)
    previous = ROOT / confirmation["previous_review_path"]
    require_hash(previous, confirmation["previous_review_sha256"])
    review = read_json(previous)
    protected = {confirmation["previous_review_path"]: confirmation["previous_review_sha256"],
                 review["input_path"]: review["input_sha256"], review["proposal_path"]: review["proposal_sha256"],
                 str(confirmation_path.relative_to(ROOT)): file_sha256(confirmation_path),
                 str(Path(__file__).relative_to(ROOT)): file_sha256(Path(__file__))}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    rows = assemble(read_json(ROOT / review["input_path"]), read_json(ROOT / review["proposal_path"]), review, confirmation)
    out = ROOT / "data/bipia/repository_scope_approved_v1"
    with new_run(out, {"protected_sha256": protected, "scope": "Human-approved class and original Chinese relation descriptions, NOT SFT targets",
                       "evaluation_exposure": "These cases inform annotation/schema design. Retain split assignments but do not claim future independent schema-generalization on them; require fresh task groups."}):
        write_json(out / "annotations.json", rows)
        write_json(out / "manifest.json", {"annotations_sha256": file_sha256(out / "annotations.json"),
                                          "class_reviewed": 24, "text_fields_reviewed": 24, "sft_ready": 0})
    print(f"Human review finalized: {out}", flush=True)


if __name__ == "__main__":
    main()
