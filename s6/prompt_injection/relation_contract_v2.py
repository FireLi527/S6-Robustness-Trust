"""Role-bearing, per-action extraction; validation never grants permissions."""
from collections import Counter

KINDS = ("execute", "prohibited", "quoted", "plan", "simulation", "unknown")
ROLES = ("object", "source", "destination", "data", "parameter", "actor", "environment", "resolved_directory")
STATES = ("explicit", "unmapped", "unspecified")


def literal(text: str, source: str) -> None:
    """Require exact nonempty source evidence without normalization."""
    if not isinstance(text, str) or not text or text not in source:
        raise ValueError("Nonliteral source evidence")


def validate(value: dict, source: str) -> None:
    """Check representation and grounding, not semantic completeness/correctness."""
    if not isinstance(value, dict) or set(value) != {"actions", "constraints", "missing_context"}:
        raise ValueError("Invalid v2 root fields")
    if not all(isinstance(value[k], list) for k in value):
        raise ValueError("Expected lists")
    for text in value["constraints"] + value["missing_context"]:
        literal(text, source)
    for index, action in enumerate(value["actions"]):
        if not isinstance(action, dict) or set(action) != {"operation", "kind", "bindings", "conditions", "evidence"}:
            raise ValueError("Invalid action fields")
        if action["kind"] not in KINDS or not isinstance(action["bindings"], list) or not action["bindings"]:
            raise ValueError("Invalid kind/bindings")
        literal(action["evidence"], source)
        literal(action["operation"], action["evidence"])
        if not isinstance(action["conditions"], list):
            raise ValueError("Expected action conditions")
        for condition in action["conditions"]:
            literal(condition, action["evidence"])
        for binding in action["bindings"]:
            validate_binding(binding, action["evidence"])


def validate_binding(binding: dict, evidence: str) -> None:
    """Unknown values stay unknown; roles preserve transfer direction."""
    if not isinstance(binding, dict) or set(binding) != {"role", "text", "status"}:
        raise ValueError("Invalid binding fields")
    if binding["role"] not in ROLES or binding["status"] not in STATES:
        raise ValueError("Invalid role/status")
    if (binding["text"] is None) != (binding["status"] == "unspecified"):
        raise ValueError("Only unspecified binding may have null text")
    if binding["text"] is not None:
        literal(binding["text"], evidence)


def units(value: dict) -> Counter:
    """Strict reference units, NOT an automatic semantic-equivalence judge."""
    result = Counter()
    for index, action in enumerate(value["actions"]):
        bindings = tuple(sorted((b["role"], b["status"], b["text"] or "") for b in action["bindings"]))
        key = (index, action["operation"], action["kind"], bindings, tuple(sorted(action["conditions"])))
        result[("action", key)] += 1
    for field in ("constraints", "missing_context"):
        result.update((field, text) for text in value[field])
    return result


def score(value: dict, source: str, expected: dict) -> dict:
    """Invalid extraction is a failure, not a benign decision."""
    validate(expected, source)
    gold = units(expected)
    try:
        validate(value, source)
        predicted = units(value)
    except (TypeError, ValueError) as error:
        return {"valid": False, "exact": False, "matched": 0, "predicted": 0,
                "reference": sum(gold.values()), "error": str(error), "tool_authorization": "not_granted"}
    return {"valid": True, "exact": predicted == gold, "matched": sum((predicted & gold).values()),
            "predicted": sum(predicted.values()), "reference": sum(gold.values()), "error": None,
            "tool_authorization": "not_granted"}
