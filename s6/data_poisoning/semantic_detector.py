"""Semantic label-anomaly detector for image candidate training data.

Unlike ``integrity_detector.py``, which only works by diffing a candidate manifest
against an independently trusted baseline manifest, this detector inspects whether
image content actually agrees with its declared candidate label. It is designed to
sit at an S6 trust boundary and is intentionally blind to ground truth: its input
type structurally excludes ``original_label`` and ``poisoned`` so a caller cannot
leak the hidden answer into a detection decision, even by accident.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


DETECTOR_NAME = "s6-semantic-label-anomaly"
DETECTOR_VERSION = "0.5.0"
CLIP_MODEL_NAME = "ViT-B-32-quickgelu"
CLIP_PRETRAINED_TAG = "openai"
EMBEDDING_MODEL = "open_clip-ViT-B-32-quickgelu-openai"
EMBEDDING_DIM = 512
EMBEDDING_PROJECTION = "none-raw-clip"

KNN_NEIGHBORS = 15
CV_FOLDS = 5
SEED = 2026

SIGNAL_WEIGHTS = {
    "neighbor_disagreement": 0.4,
    "classifier_disagreement": 0.4,
    "centroid_distance": 0.2,
}

REVIEW_THRESHOLD = 0.62
QUARANTINE_THRESHOLD = 0.75


@dataclass(frozen=True)
class SemanticInputRecord:
    """Blind detector input.

    There is no ``original_label`` or ``poisoned`` field on this type. The detector
    can only ever see the candidate label a sample was ingested with, never the
    hidden correct answer, because that answer has no attribute to read it from.
    """

    sample_id: str
    source_relpath: str
    sha256: str
    assigned_label: str


_BLIND_FIELD_NAMES = frozenset(field.name for field in fields(SemanticInputRecord))
assert "original_label" not in _BLIND_FIELD_NAMES
assert "poisoned" not in _BLIND_FIELD_NAMES


@dataclass(frozen=True)
class NeighborSample:
    sample_id: str
    assigned_label: str
    distance: float


@dataclass(frozen=True)
class SemanticSampleResult:
    sample_id: str
    decision: str
    risk_score: float
    reasons: tuple[str, ...]
    neighbor_label_agreement: float
    classifier_confidence: float | None
    centroid_distance_z: float
    neighbors: tuple[NeighborSample, ...]


@dataclass(frozen=True)
class SemanticAssessment:
    results: tuple[SemanticSampleResult, ...]
    decision_counts: dict[str, int]


def blind_record_from_row(row: Mapping[str, str]) -> SemanticInputRecord:
    """Build detector input from a candidate-only manifest row."""
    return SemanticInputRecord(
        sample_id=row["sample_id"],
        source_relpath=row["source_relpath"],
        sha256=row["sha256"],
        assigned_label=row["assigned_label"],
    )


def detector_metadata() -> dict[str, str]:
    """Return stable identity data for evaluation and audit records."""
    policy = {
        "name": DETECTOR_NAME,
        "version": DETECTOR_VERSION,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "embedding_projection": EMBEDDING_PROJECTION,
        "knn_neighbors": KNN_NEIGHBORS,
        "cv_folds": CV_FOLDS,
        "seed": SEED,
        "signal_weights": SIGNAL_WEIGHTS,
        "review_threshold": REVIEW_THRESHOLD,
        "quarantine_threshold": QUARANTINE_THRESHOLD,
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
    metadata_path = cache_path.with_suffix(".metadata.json")
    if not metadata_path.is_file() or json.loads(metadata_path.read_text()) != embedding_metadata():
        return {}
    with np.load(cache_path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def embedding_metadata() -> dict:
    return {"model": EMBEDDING_MODEL, "dimension": EMBEDDING_DIM,
            "preprocessing": "open_clip-default-rgb-v1"}


def save_embedding_cache(cache_path: Path, embeddings: Mapping[str, np.ndarray]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, **embeddings)
    cache_path.with_suffix(".metadata.json").write_text(json.dumps(embedding_metadata()), encoding="utf-8")


def extract_embeddings(
    records: Sequence[SemanticInputRecord],
    image_root: Path,
    cache_path: Path,
    model_cache_dir: Path,
    batch_size: int = 32,
) -> dict[str, np.ndarray]:
    """Return sha256 -> 512-d CLIP ViT-B/32 image embedding, computing only cache misses.

    ``model_cache_dir`` is where the pretrained CLIP weights are downloaded/cached
    (an ``external/`` subdirectory owned by the caller), kept separate from
    ``cache_path``, which stores this project's per-image embedding cache.
    """
    # Verify bytes even on cache hits: a stale declared hash must not hide a changed image.
    for record in {record.sha256: record for record in records}.values():
        image_path = (image_root / record.source_relpath).resolve()
        if not image_path.is_relative_to(image_root.resolve()):
            raise ValueError("Image path escapes dataset root")
        with image_path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != record.sha256:
                raise ValueError(f"Image hash mismatch: {record.source_relpath}")
    cache = load_embedding_cache(cache_path)
    unique_paths = {record.sha256: record.source_relpath for record in records}
    missing = {sha: relpath for sha, relpath in unique_paths.items() if sha not in cache}

    if missing:
        import open_clip
        import torch
        from PIL import Image

        model, _, preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME,
            pretrained=CLIP_PRETRAINED_TAG,
            cache_dir=str(model_cache_dir),
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()
        print(f"CLIP: {len(missing)} images on {device}", flush=True)

        items = sorted(missing.items())
        with torch.no_grad():
            for start in range(0, len(items), batch_size):
                batch = items[start : start + batch_size]
                tensors = []
                for sha, relpath in batch:
                    image_path = (image_root / relpath).resolve()
                    if not image_path.is_relative_to(image_root.resolve()):
                        raise ValueError("Image path escapes dataset root")
                    with Image.open(image_path) as source:
                        tensors.append(preprocess(source.convert("RGB")))
                batch_embeddings = model.encode_image(torch.stack(tensors).to(device)).cpu().numpy()
                for (sha, _), vector in zip(batch, batch_embeddings):
                    cache[sha] = vector.astype(np.float32)
                if start % (batch_size * 10) == 0:
                    print(f"CLIP: {min(start + batch_size, len(items))}/{len(items)}", flush=True)
        save_embedding_cache(cache_path, cache)

    return {record.sha256: cache[record.sha256] for record in records}


def _unit_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def assess_semantic(
    records: Sequence[SemanticInputRecord],
    embeddings: Mapping[str, np.ndarray],
) -> SemanticAssessment:
    """Score every record for label/content disagreement, blind to ground truth."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.neighbors import NearestNeighbors

    n = len(records)
    if n < 2:
        raise ValueError("Semantic assessment needs at least two distinct images")
    ids = [record.sample_id for record in records]
    if len(set(ids)) != n or len({record.sha256 for record in records}) != n:
        raise ValueError("Duplicate sample IDs or image hashes must be resolved before semantic scoring")
    labels = np.array([record.assigned_label for record in records])
    features = _unit_normalize(
        np.stack([embeddings[record.sha256] for record in records])
    )

    if not np.isfinite(features).all() or np.any(np.linalg.norm(features, axis=1) == 0):
        raise ValueError("Embeddings must be finite, nonzero vectors")

    k = max(min(KNN_NEIGHBORS, n - 1), 1)
    neighbor_model = NearestNeighbors(n_neighbors=k + 1, metric="cosine").fit(features)
    distances, indices = neighbor_model.kneighbors(features)

    label_counts = Counter(labels.tolist())
    min_class_count = min(label_counts.values())
    cv_folds = min(CV_FOLDS, min_class_count)
    classes_sorted = np.unique(labels)
    class_confidence = np.zeros(n)
    if cv_folds >= 2 and len(classes_sorted) >= 2:
        classifier = LogisticRegression(max_iter=1000, random_state=SEED)
        splitter = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=SEED)
        probabilities = cross_val_predict(
            classifier, features, labels, cv=splitter, method="predict_proba"
        )
        class_index = {label: index for index, label in enumerate(classes_sorted)}
        for i in range(n):
            class_confidence[i] = probabilities[i, class_index[labels[i]]]
    else:
        class_confidence[:] = np.nan

    sum_by_label: dict[str, np.ndarray] = {}
    count_by_label: dict[str, int] = {}
    for label in classes_sorted:
        mask = labels == label
        sum_by_label[label] = features[mask].sum(axis=0)
        count_by_label[label] = int(mask.sum())

    centroid_distance = np.zeros(n)
    distances_by_label: dict[str, list[float]] = defaultdict(list)
    for i in range(n):
        label = labels[i]
        count = count_by_label[label]
        if count <= 1:
            centroid = features[i]
        else:
            centroid = (sum_by_label[label] - features[i]) / (count - 1)
        distance = float(np.linalg.norm(features[i] - centroid))
        centroid_distance[i] = distance
        distances_by_label[label].append(distance)

    distance_mean = {label: float(np.mean(values)) for label, values in distances_by_label.items()}
    distance_std = {
        label: max(float(np.std(values)), 1e-6) for label, values in distances_by_label.items()
    }
    centroid_z = np.array(
        [
            (centroid_distance[i] - distance_mean[labels[i]]) / distance_std[labels[i]]
            for i in range(n)
        ]
    )

    results: list[SemanticSampleResult] = []
    for i in range(n):
        neighbor_pairs = [
            (int(j), float(d)) for j, d in zip(indices[i], distances[i]) if j != i
        ][:k]
        agreeing = sum(1 for j, _ in neighbor_pairs if labels[j] == labels[i])
        neighbor_agreement = agreeing / max(len(neighbor_pairs), 1)
        neighbor_disagreement = 1.0 - neighbor_agreement

        confidence = class_confidence[i]
        classifier_disagreement = 0.0 if np.isnan(confidence) else 1.0 - float(confidence)

        risk_centroid = float(np.clip(max(centroid_z[i], 0.0) / 3.0, 0.0, 1.0))

        risk_score = (
            SIGNAL_WEIGHTS["neighbor_disagreement"] * neighbor_disagreement
            + SIGNAL_WEIGHTS["classifier_disagreement"] * classifier_disagreement
            + SIGNAL_WEIGHTS["centroid_distance"] * risk_centroid
        )

        reasons: list[str] = []
        if neighbor_agreement < 0.5:
            disagreeing = len(neighbor_pairs) - agreeing
            reasons.append(
                f"{disagreeing} of {len(neighbor_pairs)} nearest neighbours have a "
                "different candidate label"
            )
        if not np.isnan(confidence) and confidence < 0.3:
            reasons.append(
                "cross-validated classifier assigns only "
                f"{confidence:.0%} confidence to the candidate label"
            )
        if centroid_z[i] > 1.5:
            reasons.append(
                f"embedding is {centroid_z[i]:.1f} standard deviations farther from "
                "its candidate-class centroid than typical"
            )
        if not reasons:
            reasons.append(
                "image content agrees with nearest neighbours, the cross-validated "
                "classifier, and the candidate-class centroid"
            )

        if risk_score >= QUARANTINE_THRESHOLD:
            decision = "QUARANTINE"
        elif risk_score >= REVIEW_THRESHOLD:
            decision = "REVIEW"
        else:
            decision = "ALLOW"

        neighbors = tuple(
            NeighborSample(ids[j], str(labels[j]), d) for j, d in neighbor_pairs[:5]
        )

        results.append(
            SemanticSampleResult(
                sample_id=ids[i],
                decision=decision,
                risk_score=round(float(risk_score), 4),
                reasons=tuple(reasons),
                neighbor_label_agreement=round(float(neighbor_agreement), 4),
                classifier_confidence=(
                    None if np.isnan(confidence) else round(float(confidence), 4)
                ),
                centroid_distance_z=round(float(centroid_z[i]), 4),
                neighbors=neighbors,
            )
        )

    decision_counts = dict(Counter(result.decision for result in results))
    return SemanticAssessment(results=tuple(results), decision_counts=decision_counts)
