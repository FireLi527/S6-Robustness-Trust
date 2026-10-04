"""Shared adapter from grounded model output to triage/extraction metrics."""
from s6.prompt_injection.instruction_slot_model import grounded_slot, compare, direct_decision
from s6.prompt_injection.authorization_slots_evaluation import summarize


def prediction(row: dict, records: dict, arm: str) -> dict:
    """Ground evidence before any deterministic authorization comparison."""
    if arm == "direct":
        return {"id": row["id"], "decision": direct_decision(records["direct"], row["task"], row["content"]),
                "task_slots": None, "content_slots": None, "tool_authorization": "not_granted"}
    if arm != "structured":
        raise ValueError("Unknown arm")
    task = grounded_slot(records["task"], row["task"], "task")
    body = grounded_slot(records["content"], row["content"], "content")
    decision, reason = compare(task, body)
    def metric_slot(value: dict | None) -> dict | None:
        return {"mode": value["mode"], "operation": value["operation"], "target": value["target"], "excluded": None} if value else None
    return {"id": row["id"], "decision": decision, "reason": reason,
            "task_slots": metric_slot(task), "content_slots": metric_slot(body),
            "task_evidence_valid": task is not None, "content_evidence_valid": body is not None,
            "tool_authorization": "not_granted"}


def summarize_arm(rows: list[dict], predictions: list[dict], arm: str) -> dict:
    """Excluded is an API adapter placeholder, explicitly not a measured field."""
    result = summarize(rows, predictions)
    if arm == "direct":
        result.pop("extraction")
    else:
        for side in ("task", "content"):
            result["extraction"][side]["fields"].pop("excluded")
    result["by_kind"] = {}
    for kind in sorted({r["kind"] for r in rows}):
        indices = [i for i, r in enumerate(rows) if r["kind"] == kind]
        subset = summarize([rows[i] for i in indices], [predictions[i] for i in indices])
        subset.pop("extraction")
        result["by_kind"][kind] = subset
    return result
