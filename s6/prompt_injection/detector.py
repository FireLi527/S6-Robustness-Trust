"""Explainable baseline policy for indirect prompt-injection detection.

This is intentionally a transparent research baseline, not a claim of complete
prompt-injection protection. It is designed to sit at an S6 trust boundary and
return ALLOW, BLOCK, or REVIEW with auditable reasons.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskSpan:
    start: int
    end: int
    label: str


@dataclass(frozen=True)
class DetectionResult:
    decision: str
    score: int
    reasons: tuple[str, ...]
    highlights: tuple[RiskSpan, ...]


DETECTOR_NAME = "s6-rule-prompt-injection"
DETECTOR_VERSION = "0.2.0"

REVIEW_THRESHOLD = 2
BLOCK_THRESHOLD = 4

SIGNAL_WEIGHTS = {
    "instruction_override": 6,
    "output_control": 4,
    "high_risk": 6,
    "encoded_instruction": 3,
    "prompt_like_instruction": 2,
}


_OVERRIDE = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass)\b.{0,60}"
    r"\b(?:instruction|prompt|rule|above|previous|prior|system)\b",
    re.IGNORECASE | re.DOTALL,
)

_OUTPUT_REFERENCE = re.compile(
    r"\b(?:answer|response|reply|message)\b",
    re.IGNORECASE,
)

_OUTPUT_CONTROL = re.compile(
    r"\b(?:add|augment|encode|enhance|include|integrate|modify|provide|render|"
    r"replace|reverse|shift|substitute|translate|use|write)\b",
    re.IGNORECASE,
)

_HIGH_RISK = re.compile(
    r"\b(?:bank details|password|api key|secret|lottery winnings|transfer(?:ring)? funds|"
    r"fake antivirus|fabricated statistic|false claim|baseless rumor|misleading statement)\b",
    re.IGNORECASE,
)

_PROMPT_LIKE_ENDING = re.compile(
    r"^(?:add\b|analy[sz]e\b|apply\b|augment\b|can you\b|describe\b|determine\b|"
    r"encode\b|enhance\b|express\b|help me\b|how (?:can|do) i\b|include\b|"
    r"integrate\b|is this\b|modify\b|provide\b|recommend\b|render\b|reply\b|"
    r"replace\b|reverse\b|shift\b|show me\b|suggest\b|summari[sz]e\b|"
    r"translate\b|use\b|what (?:are|is)\b|write\b)",
    re.IGNORECASE,
)

_BASE64_LINE = re.compile(r"^[A-Za-z0-9+/]{36,}={0,2}$")


def detector_metadata() -> dict[str, str]:
    """Return stable identity data for evaluation and audit records."""
    policy = {
        "name": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "review_threshold": REVIEW_THRESHOLD,
        "block_threshold": BLOCK_THRESHOLD,
        "signal_weights": SIGNAL_WEIGHTS,
        "patterns": {
            "override": {"pattern": _OVERRIDE.pattern, "flags": _OVERRIDE.flags},
            "output_reference": {
                "pattern": _OUTPUT_REFERENCE.pattern,
                "flags": _OUTPUT_REFERENCE.flags,
            },
            "output_control": {
                "pattern": _OUTPUT_CONTROL.pattern,
                "flags": _OUTPUT_CONTROL.flags,
            },
            "high_risk": {"pattern": _HIGH_RISK.pattern, "flags": _HIGH_RISK.flags},
            "prompt_like_ending": {
                "pattern": _PROMPT_LIKE_ENDING.pattern,
                "flags": _PROMPT_LIKE_ENDING.flags,
            },
            "base64_line": {
                "pattern": _BASE64_LINE.pattern,
                "flags": _BASE64_LINE.flags,
            },
        },
    }
    canonical = json.dumps(policy, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return {
        "detector": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "config_hash": hashlib.sha256(canonical).hexdigest(),
    }


def _content_lines(text: str) -> list[tuple[int, int, str]]:
    lines: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^|\r\n]+", text):
        raw = match.group()
        left_trim = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if stripped:
            start = match.start() + left_trim
            lines.append((start, start + len(stripped), stripped))
    return lines


def _is_encoded_instruction(line: str) -> bool:
    if not _BASE64_LINE.fullmatch(line):
        return False
    try:
        padded = line + "=" * (-len(line) % 4)
        decoded = base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    printable = sum(character.isprintable() for character in decoded) / max(len(decoded), 1)
    return printable > 0.9 and len(decoded.split()) >= 3


def detect_prompt_injection(text: str) -> DetectionResult:
    """Classify untrusted text and explain every policy signal."""
    score = 0
    reasons: list[str] = []
    highlights: list[RiskSpan] = []

    override_matches = list(_OVERRIDE.finditer(text))
    if override_matches:
        score += SIGNAL_WEIGHTS["instruction_override"]
        reasons.append("instruction-override language")
        highlights.extend(
            RiskSpan(match.start(), match.end(), "instruction override")
            for match in override_matches
        )

    lines = _content_lines(text)
    output_control_lines = [
        (start, end)
        for start, end, line in lines
        if _OUTPUT_REFERENCE.search(line) and _OUTPUT_CONTROL.search(line)
    ]
    if output_control_lines:
        score += SIGNAL_WEIGHTS["output_control"]
        reasons.append("attempt to control the model's output")
        highlights.extend(
            RiskSpan(start, end, "output manipulation")
            for start, end in output_control_lines
        )

    high_risk_matches = list(_HIGH_RISK.finditer(text))
    if high_risk_matches:
        score += SIGNAL_WEIGHTS["high_risk"]
        reasons.append("high-risk fraud, exfiltration, or misinformation language")
        highlights.extend(
            RiskSpan(match.start(), match.end(), "high-risk action")
            for match in high_risk_matches
        )

    encoded_lines = [
        (start, end) for start, end, line in lines if _is_encoded_instruction(line)
    ]
    if encoded_lines:
        score += SIGNAL_WEIGHTS["encoded_instruction"]
        reasons.append("decodable Base64-like instruction in untrusted content")
        highlights.extend(
            RiskSpan(start, end, "encoded instruction") for start, end in encoded_lines
        )

    prompt_lines = [
        (start, end)
        for start, end, line in lines
        if len(line) >= 25 and _PROMPT_LIKE_ENDING.search(line)
    ]
    if prompt_lines:
        score += SIGNAL_WEIGHTS["prompt_like_instruction"]
        reasons.append("standalone prompt-like instruction in untrusted content")
        highlights.extend(
            RiskSpan(start, end, "prompt-like instruction")
            for start, end in prompt_lines
        )

    if score >= BLOCK_THRESHOLD:
        decision = "BLOCK"
    elif score >= REVIEW_THRESHOLD:
        decision = "REVIEW"
    else:
        decision = "ALLOW"

    unique_highlights = {
        (highlight.start, highlight.end, highlight.label): highlight
        for highlight in highlights
    }
    ordered_highlights = tuple(
        sorted(unique_highlights.values(), key=lambda item: (item.start, item.end))
    )
    return DetectionResult(decision, score, tuple(reasons), ordered_highlights)
