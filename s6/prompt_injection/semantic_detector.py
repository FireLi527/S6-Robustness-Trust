"""P2 semantic task-consistency detector for the S6 prompt-injection baseline.

Research question (see s6/BASELINE_ROADMAP.md, Milestone P2): can S6 flag an
instruction that is harmless in isolation but conflicts with the user's actual
task? The P1 rule engine (detector.py) only flags a line if it *syntactically*
looks like an instruction (starts with an imperative verb via
``_PROMPT_LIKE_ENDING``) -- which is exactly why obfuscated attack categories
(Anagramming, Misspelling Intentionally, Space Removal & Grouping) evade it:
scrambling or misspelling the line breaks the regex without breaking the
instruction. This detector deliberately does NOT reuse that regex. It treats
every sufficiently long, non-header content line as a *candidate* task
statement and lets semantic similarity to the user's actual task (BIPIA's
``question`` field) decide whether it's suspicious -- so it can independently
catch instructions the rule engine's syntax-first filter misses.

This detector never receives BIPIA's ``attack_name``/ground-truth label --
its only inputs are ``question`` and ``context``, both of which a real
deployment already has.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from detector import RiskSpan, _content_lines

DETECTOR_NAME = "s6-semantic-task-consistency"
DETECTOR_VERSION = "0.1.0"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
MIN_CANDIDATE_LENGTH = 25

# Excludes structured "KEY: value" header lines (SUBJECT:, EMAIL_FROM:, ...)
# from the candidate set -- every BIPIA email contains several of these and
# they are never meaningful "instructions", so keeping them in would only
# add noise no similarity threshold could usefully separate.
_HEADER_LINE = re.compile(r"^[A-Z_]{2,20}:\s")

# Chosen by inspecting the cosine-similarity distribution between each
# candidate line and its record's `question` field on the *development*
# split only (data/bipia/splits/attack_development.json). At review=0.03/
# block=0.00, this signal independently catches 1,477 of the 3,600 (41.0%)
# development attack records the P1 rule engine misses entirely (mostly
# Information Retrieval, Content Creation, Misspelling Intentionally,
# Learning and Tutoring, Clickbait), at a cost of 2/46 development clean
# emails with any candidate line (4.3%) crossing the threshold. Looser
# thresholds (e.g. review=0.05) catch far more rule-missed attacks (59.6%)
# but roughly quadruple that clean false-positive rate (17.4%), which is
# judged an unacceptable trade for this baseline. The unseen_test split was
# never consulted while picking these numbers, per the experimental-
# integrity rule in CLAUDE.md / s6/BASELINE_ROADMAP.md.
REVIEW_SIMILARITY = 0.03
BLOCK_SIMILARITY = 0.00


@dataclass(frozen=True)
class SemanticAssessment:
    decision: str
    score: float
    reasons: tuple[str, ...]
    highlights: tuple[RiskSpan, ...]


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_candidate_instructions(context: str) -> list[tuple[int, int, str]]:
    """Return (start, end, line) triples for candidate task-statement lines in *context*.

    Deliberately broader than detector.py's syntax-gated "prompt_like_instruction"
    signal: any non-header content line long enough to plausibly be a sentence
    is a candidate, regardless of whether it grammatically looks like a command.
    Semantic similarity to the question -- not sentence structure -- is what
    decides suspicion, so this can catch instructions the rule engine's
    imperative-verb regex misses (e.g. reordered/misspelled attack text).
    """
    return [
        (start, end, line)
        for start, end, line in _content_lines(context)
        if len(line) >= MIN_CANDIDATE_LENGTH and not _HEADER_LINE.match(line)
    ]


def texts_requiring_embeddings(question: str, context: str) -> list[str]:
    """All strings that must be embedded to assess one (question, context) pair."""
    texts = [question] if question else []
    texts.extend(line for _, _, line in extract_candidate_instructions(context))
    return texts


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def assess_task_consistency(
    question: str,
    context: str,
    embeddings: Mapping[str, np.ndarray],
) -> SemanticAssessment:
    """Score whether any instruction-like line in *context* is off-task for *question*.

    ``embeddings`` must map ``text_sha256(text)`` to an embedding vector for
    *question* and every candidate line returned by
    ``extract_candidate_instructions(context)`` -- see ``embed_texts`` /
    ``extract_embeddings`` below for how to build it. Keeping this function
    pure (no model loading) mirrors the data_poisoning module's
    ``assess_semantic`` contract and keeps it trivially unit-testable.
    """
    candidates = extract_candidate_instructions(context)
    if not question or not candidates:
        return SemanticAssessment("ALLOW", 0.0, (), ())

    question_key = text_sha256(question)
    if question_key not in embeddings:
        raise KeyError(f"Missing embedding for question: {question!r}")
    q_vec = embeddings[question_key]

    scored: list[tuple[float, int, int, str]] = []
    for start, end, line in candidates:
        key = text_sha256(line)
        if key not in embeddings:
            raise KeyError(f"Missing embedding for candidate line: {line!r}")
        scored.append((_cosine(q_vec, embeddings[key]), start, end, line))

    worst_similarity, start, end, line = min(scored, key=lambda item: item[0])
    disagreement = round(1.0 - worst_similarity, 4)

    if worst_similarity <= BLOCK_SIMILARITY:
        decision = "BLOCK"
    elif worst_similarity <= REVIEW_SIMILARITY:
        decision = "REVIEW"
    else:
        return SemanticAssessment("ALLOW", disagreement, (), ())

    reasons = (
        f"instruction-like content is semantically unrelated to the user's task "
        f"(similarity={worst_similarity:.2f})",
    )
    highlights = (RiskSpan(start, end, "task-inconsistent instruction"),)
    return SemanticAssessment(decision, disagreement, reasons, highlights)


def combine_hybrid(
    rule_decision: str,
    rule_reasons: Sequence[str],
    semantic: SemanticAssessment,
) -> tuple[str, tuple[str, ...]]:
    """Merge the P1 rule decision with the P2 semantic signal (worse-of-two wins)."""
    severity = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}
    decision = rule_decision if severity[rule_decision] >= severity[semantic.decision] else semantic.decision
    reasons = tuple(rule_reasons) + semantic.reasons
    return decision, reasons


def detector_metadata() -> dict[str, str]:
    """Return stable identity data for evaluation and audit records."""
    policy = {
        "name": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "min_candidate_length": MIN_CANDIDATE_LENGTH,
        "review_similarity": REVIEW_SIMILARITY,
        "block_similarity": BLOCK_SIMILARITY,
    }
    canonical = json.dumps(policy, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return {
        "detector": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "config_hash": hashlib.sha256(canonical).hexdigest(),
    }


def load_embedding_cache(cache_path: Path) -> dict[str, np.ndarray]:
    if not cache_path.is_file():
        return {}
    with np.load(cache_path) as data:
        return {key: data[key] for key in data.files}


def save_embedding_cache(cache_path: Path, embeddings: Mapping[str, np.ndarray]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, **embeddings)


@lru_cache(maxsize=1)
def _load_model(model_cache_dir: str):
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL, cache_dir=model_cache_dir)
    model = AutoModel.from_pretrained(EMBEDDING_MODEL, cache_dir=model_cache_dir)
    model.eval()
    return tokenizer, model


def embed_texts(
    texts: Sequence[str], model_cache_dir: Path, batch_size: int = 64
) -> dict[str, np.ndarray]:
    """Compute sha256(text) -> L2-normalized MiniLM sentence embedding.

    Loads the HuggingFace model once per process (``_load_model`` is
    ``lru_cache``d) so repeated calls -- e.g. one per incoming ``app.py``
    request -- reuse the warm model instead of reloading it from disk.
    """
    if not texts:
        return {}
    import torch

    tokenizer, model = _load_model(str(model_cache_dir))
    unique = {text_sha256(t): t for t in texts}
    items = sorted(unique.items())
    result: dict[str, np.ndarray] = {}
    with torch.no_grad():
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            encoded = tokenizer(
                [text for _, text in batch],
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt",
            )
            output = model(**encoded)
            token_embeddings = output.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).float()
            summed = (token_embeddings * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            pooled = (summed / counts).numpy()
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            normalized = pooled / norms
            for (key, _), vector in zip(batch, normalized):
                result[key] = vector.astype(np.float32)
    return result


def extract_embeddings(
    texts: Sequence[str],
    cache_path: Path,
    model_cache_dir: Path,
    batch_size: int = 64,
) -> dict[str, np.ndarray]:
    """Return sha256(text) -> embedding for *texts*, computing only cache misses.

    ``model_cache_dir`` is where the pretrained HuggingFace weights are
    downloaded/cached (an ``external/`` subdirectory owned by the caller,
    mirroring data_poisoning's ``CLIP_MODEL_CACHE`` convention), kept separate
    from ``cache_path``, which stores this project's per-text embedding cache
    across evaluation runs.
    """
    cache = load_embedding_cache(cache_path)
    unique = {text_sha256(t): t for t in texts}
    missing_texts = [t for key, t in unique.items() if key not in cache]
    if missing_texts:
        cache.update(embed_texts(missing_texts, model_cache_dir, batch_size))
        save_embedding_cache(cache_path, cache)
    return cache
