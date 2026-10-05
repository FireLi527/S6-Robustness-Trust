"""Registration-time trusted tool manifest, for same-theme attacks semantic alignment cannot catch.

The manifest is built once per agent from its declared non-malicious tool catalog (provenance ==
"normal"), independent of any specific request or attack instance -- the same capability-scoping
philosophy as tool_policy.TOOL_REGISTRY. The per-call decision function below never sees provenance
or any other ground-truth field; it only checks set membership.
"""


def manifest(agents: list[dict]) -> dict[str, frozenset[str]]:
    """One-time registration: per agent, the tool names its own normal catalog declares."""
    return {a["agent"]: frozenset(t["name"] for t in a["tools"] if t["provenance"] == "normal") for a in agents}


def decide(tool_name: str, trusted: frozenset[str]) -> bool:
    """Blind to provenance: auto-allow only tools already in the registered manifest."""
    return tool_name in trusted
