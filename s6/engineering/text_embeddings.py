"""Frozen local MiniLM with complete token-window coverage and versioned caches."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from s6.engineering.artifacts import atomic_binary, file_sha256


@dataclass(frozen=True)
class EncodingConfig:
    strategy: str = "chunked"
    window_tokens: int = 256
    overlap_tokens: int = 32
    batch_size: int = 16
    max_document_tokens: int = 100_000

    def validate(self, position_limit: int, special_tokens: int) -> None:
        if self.strategy not in {"chunked", "legacy_prefix_128"}:
            raise ValueError("Unknown encoding strategy")
        if not special_tokens < self.window_tokens <= position_limit:
            raise ValueError("Window exceeds model capacity or has no payload capacity")
        if not 0 <= self.overlap_tokens < self.window_tokens - special_tokens:
            raise ValueError("Overlap must be smaller than the payload window")
        if self.batch_size < 1 or self.max_document_tokens < 1:
            raise ValueError("Batch size and resource limit must be positive")
        if self.strategy == "legacy_prefix_128" and self.window_tokens != 128:
            raise ValueError("Legacy control must explicitly use a 128-token window")


def token_windows(length: int, capacity: int, overlap: int) -> list[tuple[int, int]]:
    """Offsets cover every payload token, including a final short window."""
    if length < 0 or capacity < 1 or not 0 <= overlap < capacity:
        raise ValueError("Invalid window bounds")
    windows = []
    start = 0
    while True:
        end = min(start + capacity, length)
        windows.append((start, end))
        if end == length:
            return windows
        start = end - overlap


def coverage_weights(length: int, windows: Sequence[tuple[int, int]]) -> np.ndarray:
    """Share overlap weight so each payload token contributes total weight one."""
    if length == 0:
        return np.ones(len(windows), dtype=np.float64)
    coverage = np.zeros(length, dtype=np.int64)
    for start, end in windows:
        coverage[start:end] += 1
    if np.any(coverage == 0):
        raise ValueError("Incomplete token coverage")
    return np.array([np.sum(1.0 / coverage[start:end]) for start, end in windows])


class LocalTextEncoder:
    """Public encoder API; never invokes an LLM, executes text or downloads weights."""

    def __init__(self, snapshot: Path, cache: Path, config: EncodingConfig):
        from transformers import AutoModel, AutoTokenizer

        self.config, self.cache = config, cache
        required = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
                    "special_tokens_map.json", "vocab.txt")
        hashes = {name: file_sha256(snapshot / name) for name in required}
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        self.model = AutoModel.from_pretrained(snapshot, local_files_only=True)
        self.model.eval()
        self.model.requires_grad_(False)
        self.special_tokens = self.tokenizer.num_special_tokens_to_add(pair=False)
        if (self.model.config.model_type != "bert" or self.special_tokens != 2
                or any(value is None for value in (self.tokenizer.cls_token_id,
                                                   self.tokenizer.sep_token_id,
                                                   self.tokenizer.pad_token_id))):
            raise ValueError("This encoder requires the MiniLM BERT single-sequence token layout")
        config.validate(self.model.config.max_position_embeddings, self.special_tokens)
        self.metadata = {"model_files": hashes, "snapshot": snapshot.name, "config": asdict(config),
                         "pooling": "mean-attention-window-l2/inverse-overlap-document-mean-l2-v1",
                         "implementation_sha256": file_sha256(Path(__file__))}
        canonical = json.dumps(self.metadata, sort_keys=True).encode()
        self.fingerprint = hashlib.sha256(canonical).hexdigest()

    def encode(self, texts: Sequence[str]) -> tuple[np.ndarray, list[dict]]:
        if not texts:
            return np.empty((0, self.model.config.hidden_size), dtype=np.float32), []
        records = [self.encode_one(text) for text in texts]
        return np.stack([item[0] for item in records]), [item[1] for item in records]

    def encode_one(self, text: str) -> tuple[np.ndarray, dict]:
        import torch

        if not isinstance(text, str):
            raise TypeError("Encoder input must be text")
        if len(text) > self.config.max_document_tokens * 16:
            raise ValueError("Document exceeds character resource limit")
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        path = self.cache / self.fingerprint / f"{text_hash}.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as saved:
                vector = saved["vector"]
                stats = json.loads(str(saved["metadata"].item()))
            if (stats.get("encoder") != self.fingerprint or stats.get("text_sha256") != text_hash
                    or vector.shape != (self.model.config.hidden_size,) or not np.isfinite(vector).all()):
                raise ValueError(f"Invalid embedding cache: {path}")
            return vector, stats
        ids = self.tokenizer.encode(text, add_special_tokens=False, truncation=False)
        if len(ids) > self.config.max_document_tokens:
            raise ValueError("Document exceeds token resource limit; nothing was silently truncated")
        capacity = self.config.window_tokens - self.special_tokens
        if self.config.strategy == "legacy_prefix_128":
            windows = [(0, min(len(ids), capacity))]
        else:
            windows = token_windows(len(ids), capacity, self.config.overlap_tokens)
        weights = coverage_weights(len(ids), windows) if self.config.strategy == "chunked" else np.ones(1)
        vectors = []
        with torch.inference_mode():
            for offset in range(0, len(windows), self.config.batch_size):
                batch = []
                for start, end in windows[offset:offset + self.config.batch_size]:
                    batch.append([self.tokenizer.cls_token_id, *ids[start:end], self.tokenizer.sep_token_id])
                width = max(map(len, batch))
                input_ids = torch.tensor([tokens + [self.tokenizer.pad_token_id] * (width - len(tokens))
                                          for tokens in batch], dtype=torch.long)
                attention = torch.tensor([[1] * len(tokens) + [0] * (width - len(tokens))
                                          for tokens in batch], dtype=torch.long)
                encoded = {"input_ids": input_ids, "attention_mask": attention,
                           "token_type_ids": torch.zeros_like(input_ids)}
                hidden = self.model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).float()
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                vectors.extend(torch.nn.functional.normalize(pooled, p=2, dim=1).cpu().numpy())
        vector = np.average(np.stack(vectors), axis=0, weights=weights)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError("Invalid pooled embedding")
        vector = (vector / norm).astype(np.float32)
        covered = windows[-1][1]
        stats = {"encoder": self.fingerprint, "text_sha256": text_hash, "input_tokens": len(ids),
                 "covered_tokens": covered, "dropped_tokens": len(ids) - covered, "chunks": len(windows)}
        atomic_binary(path, lambda stream: np.savez_compressed(stream, vector=vector,
                                                               metadata=json.dumps(stats, sort_keys=True)))
        return vector, stats
