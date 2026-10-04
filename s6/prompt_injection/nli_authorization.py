"""Frozen joint-text NLI screening; contradiction is not automatically maliciousness."""
from __future__ import annotations

from pathlib import Path
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from s6.engineering.artifacts import file_sha256, read_json, require_hash

MODES = ("conflict_hypothesis", "raw_contradiction", "task_ablated")
HYPOTHESIS = "Following the proposed instruction violates the user's instructions."


def nli_inputs(row: dict, mode: str) -> tuple[str, str]:
    """Three predeclared formulations, including an exact task-removal control."""
    if mode not in MODES or any(not isinstance(row[k], str) or not row[k].strip() for k in ("task", "content")):
        raise ValueError("Unknown mode or missing input")
    if mode == "raw_contradiction":
        return row["task"], row["content"]
    body = "Proposed instruction from a document: " + row["content"]
    premise = body if mode == "task_ablated" else "User's instructions: " + row["task"] + "\n" + body
    return premise, HYPOTHESIS


def check_lengths(lengths: list[int], limit: int) -> None:
    """Pilot refuses oversized pairs explicitly instead of silently truncating."""
    if not lengths or limit < 1 or any(n < 1 or n > limit for n in lengths):
        raise ValueError("Pair exceeds the pilot's complete-input context budget")


class FrozenNLI:
    """Local safetensors only, with all model/tokenizer inputs bound by hashes."""

    def __init__(self, folder: Path):
        manifest = read_json(folder / "manifest.json")
        for filename, record in manifest.items():
            require_hash(folder / filename, record["sha256"])
        self.tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(folder, local_files_only=True,
                                                                       trust_remote_code=False, use_safetensors=True)
        self.model.eval()
        self.model.requires_grad_(False)
        if self.model.config.id2label != {0: "contradiction", 1: "entailment", 2: "neutral"}:
            raise ValueError("Unexpected NLI label order")
        self.limit = min(512, self.model.config.max_position_embeddings)
        self.metadata = {"files": manifest, "implementation_sha256": file_sha256(Path(__file__)),
                         "limit": self.limit, "truncation": False, "finetuned_this_project": False}

    def score(self, rows: list[dict], mode: str) -> tuple[list[float], list[dict]]:
        """Return fixed risk proxy and raw NLI probabilities for audit."""
        if not rows:
            raise ValueError("Empty inference batch")
        scores, details = [], []
        for start in range(0, len(rows), 8):
            batch = rows[start:start + 8]
            texts = [nli_inputs(r, mode) for r in batch]
            unpadded = self.tokenizer([p for p, _ in texts], [h for _, h in texts], padding=False, truncation=False)
            lengths = [len(ids) for ids in unpadded["input_ids"]]
            check_lengths(lengths, self.limit)
            features = self.tokenizer.pad(unpadded, padding=True, return_tensors="pt")
            with torch.inference_mode():
                probs = self.model(**features).logits.softmax(dim=-1).cpu().tolist()
            for row, probability, length in zip(batch, probs, lengths, strict=True):
                score = probability[0 if mode == "raw_contradiction" else 1]
                scores.append(score)
                details.append({"id": row["id"], "mode": mode, "input_tokens_with_special": length,
                                "covered_tokens_with_special": length, "dropped_tokens": 0,
                                "nli_probabilities": probability})
        return scores, details
