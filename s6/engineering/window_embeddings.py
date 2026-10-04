"""Window-level embeddings extending the frozen public document encoder API."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from s6.engineering.artifacts import atomic_binary, file_sha256
from s6.engineering.text_embeddings import LocalTextEncoder, coverage_weights, token_windows


def pooled_document(vectors: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Reproduce normalized, inverse-overlap-weighted full-document mean."""
    if (vectors.ndim != 2 or weights.shape != (len(vectors),) or not len(vectors)
            or not np.isfinite(vectors).all() or not np.isfinite(weights).all()
            or np.any(weights <= 0)):
        raise ValueError("Invalid window vectors or weights")
    vector = np.average(vectors, axis=0, weights=weights)
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError("Invalid document embedding")
    return (vector / norm).astype(np.float32)


class WindowTextEncoder(LocalTextEncoder):
    """Expose complete windows without modifying prior encoder code or caches.

Uses the public tokenizer/model/config fields of LocalTextEncoder. BERT forward
pooling is intentionally versioned here because the original run froze that file.
"""

    def encode_windows(self, text: str) -> tuple[np.ndarray, np.ndarray, dict]:
        if self.config.strategy != "chunked":
            raise ValueError("Window API requires full-coverage chunked encoding")
        if not isinstance(text, str):
            raise TypeError("Encoder input must be text")
        if len(text) > self.config.max_document_tokens * 16:
            raise ValueError("Document exceeds character resource limit")
        identity = {"document_encoder": self.fingerprint,
                    "window_implementation": file_sha256(Path(__file__))}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        path = self.cache / "windows" / fingerprint / f"{text_hash}.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as saved:
                vectors, weights = saved["vectors"], saved["weights"]
                stats = json.loads(str(saved["metadata"].item()))
            if (stats.get("encoder") != fingerprint or stats.get("text_sha256") != text_hash
                    or vectors.ndim != 2 or vectors.shape[1] != self.model.config.hidden_size
                    or stats.get("chunks") != len(vectors) or stats.get("dropped_tokens") != 0):
                raise ValueError(f"Invalid window cache: {path}")
            pooled_document(vectors, weights)  # Shape/finite/weight validation on cache reads.
            return vectors, weights, stats
        ids = self.tokenizer.encode(text, add_special_tokens=False, truncation=False)
        if len(ids) > self.config.max_document_tokens:
            raise ValueError("Document exceeds token limit; no windows silently dropped")
        windows = token_windows(len(ids), self.config.window_tokens - self.special_tokens,
                                self.config.overlap_tokens)
        weights = coverage_weights(len(ids), windows)
        vectors = self.forward_windows(ids, windows)
        stats = {"encoder": fingerprint, "text_sha256": text_hash, "input_tokens": len(ids),
                 "covered_tokens": windows[-1][1], "dropped_tokens": len(ids) - windows[-1][1],
                 "chunks": len(windows), "offsets": windows}
        atomic_binary(path, lambda stream: np.savez_compressed(stream, vectors=vectors,
                                                               weights=weights, metadata=json.dumps(stats)))
        return vectors, weights, stats

    def forward_windows(self, ids: list[int], windows: list[tuple[int, int]]) -> np.ndarray:
        """Frozen BERT inference on exact token slices, never decode/re-tokenize."""
        import torch

        if not windows or any(not 0 <= start <= end <= len(ids) or
                              end - start + self.special_tokens > self.config.window_tokens
                              for start, end in windows):
            raise ValueError("Window offsets exceed token sequence or configured capacity")
        vectors = []
        with torch.inference_mode():
            for offset in range(0, len(windows), self.config.batch_size):
                batch = [[self.tokenizer.cls_token_id, *ids[start:end], self.tokenizer.sep_token_id]
                         for start, end in windows[offset:offset + self.config.batch_size]]
                width = max(map(len, batch))
                ids_tensor = torch.tensor([tokens + [self.tokenizer.pad_token_id] * (width - len(tokens))
                                           for tokens in batch], dtype=torch.long)
                attention = torch.tensor([[1] * len(tokens) + [0] * (width - len(tokens))
                                          for tokens in batch], dtype=torch.long)
                hidden = self.model(input_ids=ids_tensor, attention_mask=attention,
                                    token_type_ids=torch.zeros_like(ids_tensor)).last_hidden_state
                mask = attention.unsqueeze(-1).float()
                mean = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                vectors.extend(torch.nn.functional.normalize(mean, p=2, dim=1).cpu().numpy())
        return np.stack(vectors).astype(np.float32)
