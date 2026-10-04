"""Shared validation for live detection and approval requests; no policy decisions."""
from __future__ import annotations

from typing import Mapping

from tool_policy import ToolCall


def content_text(payload: Mapping[str, object]) -> str:
    """Require non-empty text without changing whitespace used by task binding."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    return text


def tool_call(payload: Mapping[str, object], *, required: bool = False) -> ToolCall:
    """Validate one exact call consistently at detection, confirmation and approval."""
    name = payload.get("tool_name", "")
    if not isinstance(name, str):
        raise ValueError("tool_name must be a string")
    if required and not name.strip():
        raise ValueError("tool_name must be a non-empty string")
    target = payload.get("target", "")
    if not isinstance(target, str):
        raise ValueError("target must be a string")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in parameters.items()
    ):
        raise ValueError("parameters must contain string keys and values")
    return ToolCall(name.strip(), target.strip(), dict(parameters))
