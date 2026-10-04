"""Generic text blocks for offline repository-file detection; executes no input."""
from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    kind: str
    text: str


def extract_blocks(text: str, window: int = 1200, overlap: int = 200) -> list[Block]:
    """Include full text plus paragraph/comment views, independent of labels.

    Python comments use tokenize (even an incomplete file may yield comments).
    Markdown/HTML and slash comments are text heuristics, not syntax validation.
    Long blocks use overlapping character windows; no tail is discarded.
    """
    if window <= 0 or overlap < 0 or overlap >= window:
        raise ValueError("Require window > overlap >= 0")
    blocks = [Block("full", text)]
    seen = {text}

    def add(kind: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        start = 0
        while start < len(value):
            part = value[start:start + window]
            if part not in seen:
                seen.add(part)
                blocks.append(Block(kind, part))
            if start + window >= len(value):
                break
            start += window - overlap

    for match in re.finditer(r"[^\n]+(?:\n(?![ \t]*\n)[^\n]+)*", text):
        add("paragraph", match.group())

    comments = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                comments.append((token.start[0], token.string[1:].lstrip()))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # Paragraphs retain the full malformed input without executing it.
    run, last_line = [], -2
    for line, comment in comments:
        if line > last_line + 1 and run:
            add("python_comment", "\n".join(run))
            run = []
        run.append(comment)
        last_line = line
    add("python_comment", "\n".join(run))

    for match in re.finditer(r"<!--(.*?)-->", text, re.S):
        add("html_comment", match.group(1))
    for match in re.finditer(r"^\s*\[//\]:\s*#\s*\((.*)\)\s*$", text, re.M):
        add("markdown_hidden_comment", match.group(1))
    for match in re.finditer(r"/\*(.*?)\*/", text, re.S):
        add("slash_block_comment", re.sub(r"(?m)^\s*\* ?", "", match.group(1)))
    run = []
    for line in text.splitlines() + [""]:
        if line.lstrip().startswith("//"):
            run.append(line.lstrip()[2:].lstrip())
        elif run:
            add("slash_line_comment", "\n".join(run))
            run = []
    return blocks


def score_documents(pipeline, texts: list[str], batch_size: int = 128) -> list[dict]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    results = []
    for text in texts:
        blocks = extract_blocks(text)
        scores = []
        for start in range(0, len(blocks), batch_size):
            scores.extend(float(v) for v in pipeline.predict_proba(
                [b.text for b in blocks[start:start + batch_size]])[:, 1])
        winner = max(range(len(scores)), key=scores.__getitem__)
        results.append({"full_score": scores[0], "block_score": scores[winner],
                        "winning_kind": blocks[winner].kind, "block_count": len(blocks)})
    return results
