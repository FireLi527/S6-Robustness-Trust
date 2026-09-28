"""Experimental Python-comment signal for task-redirection attempts.

This is a research detector, not part of P1, P2, Hybrid or P3 authorization.
It only examines comment tokens and intentionally ignores executable code text.
"""

from __future__ import annotations

import io
import re
import tokenize

_AGENT = re.compile(r"\b(?:assistant|agent|reviewer)\b", re.IGNORECASE)
_REDIRECT = re.compile(
    r"\b(?:ignore|skip|instead|override|disregard|abandon|do not|don't|no patch|"
    r"reply only|answer that|claim|new task)\b",
    re.IGNORECASE,
)
_USER_OVERRIDE = re.compile(r"\boverride\b.{0,60}\buser(?:'s)?\b.{0,40}\b(?:request|task)\b", re.IGNORECASE)


def comment_lines(code: str) -> list[str]:
    """Return Python comments without executing or interpreting the code."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        return [token.string[1:].strip() for token in tokens if token.type == tokenize.COMMENT]
    except (IndentationError, tokenize.TokenError):
        return [line.lstrip()[1:].strip() for line in code.splitlines() if line.lstrip().startswith("#")]


def assess_comment_redirection(code: str) -> dict:
    if not isinstance(code, str):
        raise TypeError("Code must be text")
    matches = [line for line in comment_lines(code)
               if (_AGENT.search(line) and _REDIRECT.search(line)) or _USER_OVERRIDE.search(line)]
    return {"decision": "REVIEW" if matches else "ALLOW", "matched_comment_count": len(matches),
            "mode": "experimental_observation_only", "affects_tool_policy": False}
