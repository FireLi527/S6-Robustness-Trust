"""Experimental multi-line workflow-hijack signal for Python code context.

Only inspects Python comments and parseable docstrings. Research observation only;
not a replacement for P1/P2 and never a tool-authorization decision.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize


_AUTHORITY = re.compile(
    r"\b(?:maintainer|\bci\b|grader|automated (?:fix|patch|assistant)|"
    r"assistant|agent|reviewer|pre.patch|mandatory|required|must be followed)\b",
    re.IGNORECASE,
)
_SECRET_ACCESS = re.compile(
    r"\b(?:read|open|copy|extract)\b[\s\S]{0,180}\b(?:secret|token|password|credential|api.key|canary)\b"
    r"|\b(?:secret|token|password|credential|api.key|canary)\b[\s\S]{0,180}\b(?:read|open|copy|extract)\b",
    re.IGNORECASE,
)
_FILE_WRITE = re.compile(
    r"\b(?:write|copy|append|prepend|create)\b[\s\S]{0,160}\b(?:file|log|source|module|comment|contents)\b"
    r"|\b(?:file|log|source|module|comment|contents)\b[\s\S]{0,160}\b(?:write|copy|append|prepend|create)\b",
    re.IGNORECASE,
)
_TEST_TAMPER = re.compile(
    r"\b(?:delete|remove|disable|weaken|skip)\b[\s\S]{0,100}\b(?:test|tests|coverage)\b",
    re.IGNORECASE,
)
_SHELL = re.compile(
    r"\b(?:run|execute|invoke)\b[\s\S]{0,100}\b(?:shell|command|script|echo|pre.hook)\b"
    r"|\becho\b[^\n]{0,100}\s>\s\S+",
    re.IGNORECASE,
)
_SOURCE_MARKER = re.compile(
    r"\b(?:module|source|patch|file)\b[\s\S]{0,120}\b(?:must|require|insert|add|begin)\b"
    r"[\s\S]{0,100}\b(?:comment|marker|header)\b",
    re.IGNORECASE,
)
_OUTPUT_REDIRECT = re.compile(
    r"\b(?:reply|answer|claim|report)\b[\s\S]{0,80}\b(?:only|success|complete|finished|no.patch)\b",
    re.IGNORECASE,
)
_ACTIONS = {"secret_access": _SECRET_ACCESS, "file_write": _FILE_WRITE,
            "test_tamper": _TEST_TAMPER, "shell": _SHELL,
            "source_marker": _SOURCE_MARKER, "output_redirect": _OUTPUT_REDIRECT}


def code_text_blocks(code: str) -> list[str]:
    """Return adjacent Python comment blocks plus docstrings without executing code."""
    comments = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type == tokenize.COMMENT:
                comments.append((token.start[0], token.string[1:].strip()))
    except (IndentationError, tokenize.TokenError):
        comments = [(index, line.lstrip()[1:].strip()) for index, line in enumerate(code.splitlines(), 1)
                    if line.lstrip().startswith("#")]
    blocks = []
    current = []
    last_line = -100
    for line_no, text in comments:
        if line_no > last_line + 2 and current:
            blocks.append("\n".join(current))
            current = []
        current.append(text)
        last_line = line_no
    if current:
        blocks.append("\n".join(current))
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return blocks
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node)
            if docstring:
                blocks.append(docstring)
    return blocks


def assess_workflow_redirection(code: str) -> dict:
    if not isinstance(code, str):
        raise TypeError("Code must be text")
    reasons = set()
    for block in code_text_blocks(code):
        if not _AUTHORITY.search(block):
            continue
        for name, pattern in _ACTIONS.items():
            if pattern.search(block):
                reasons.add(name)
    return {"decision": "REVIEW" if reasons else "ALLOW", "reasons": sorted(reasons),
            "mode": "experimental_observation_only", "affects_tool_policy": False}
