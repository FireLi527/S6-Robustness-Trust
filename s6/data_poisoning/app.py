"""Run the IP102 manifest-integrity detector as a local browser application."""

from __future__ import annotations

import argparse
import csv
import json
import random
import threading
import webbrowser
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from integrity_detector import assess_manifest
from manifest_protocol import load_candidate_manifest
from semantic_detector import (
    SemanticSampleResult,
    assess_semantic,
    blind_record_from_row,
    detector_metadata,
    extract_embeddings,
    fit_trusted_projection,
)


HOST = "127.0.0.1"
PORT = 8766
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[1]
INDEX_FILE = APP_DIR / "web" / "index.html"
IP102_ROOT = PROJECT_ROOT / "external" / "IP102"
MANIFEST_ROOT = PROJECT_ROOT / "data" / "ip102_poisoning" / "manifests"
EMBEDDING_CACHE = (
    PROJECT_ROOT / "data" / "ip102_poisoning" / "embeddings" / "clip_vit_b32_embeddings.npz"
)
CLIP_MODEL_CACHE = PROJECT_ROOT / "external" / "clip_cache"
TRUSTED_MANIFEST = MANIFEST_ROOT / "clean_subset.csv"
SEMANTIC_SUMMARY_FILE = (
    PROJECT_ROOT / "results" / "ip102_poisoning" / "semantic_evaluation_summary.json"
)
SEMANTIC_SAMPLE_RESULTS_FILE = (
    PROJECT_ROOT / "results" / "ip102_poisoning" / "semantic_sample_results.json"
)
DATASETS = (
    "clean_subset",
    "label_flip_05",
    "label_flip_10",
    "targeted_0_to_1",
)
_TRUSTED_PROJECTION_LOCK = threading.Lock()
_TRUSTED_PROJECTION_CACHE = None
_SEMANTIC_ASSESSMENT_LOCK = threading.Lock()
_SEMANTIC_ASSESSMENT_CACHE: dict[str, object] = {}


@lru_cache(maxsize=8)
def load_manifest(name: str) -> tuple[dict[str, str], ...]:
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset: {name}")
    return tuple(load_candidate_manifest(MANIFEST_ROOT / f"{name}.csv"))


@lru_cache(maxsize=1)
def class_names() -> dict[str, str]:
    names: dict[str, str] = {}
    classes_file = IP102_ROOT / "classes.txt"
    for folder_label, line in enumerate(classes_file.read_text(encoding="utf-8").splitlines()):
        parts = line.strip().split(maxsplit=1)
        names[str(folder_label)] = parts[1].strip() if len(parts) == 2 else parts[0]
    return names


def assessment_payload(name: str) -> dict:
    assessment = assess_manifest(TRUSTED_MANIFEST, MANIFEST_ROOT / f"{name}.csv")
    return {
        "dataset": name,
        "decision": assessment.decision,
        "risk_score": assessment.risk_score,
        "reasons": list(assessment.reasons),
        "candidate_samples": assessment.candidate_samples,
        "label_changes": assessment.label_changes,
        "hash_changes": assessment.hash_changes,
        "missing_samples": assessment.missing_samples,
        "unknown_samples": assessment.unknown_samples,
        "duplicate_ids": assessment.duplicate_ids,
        "distribution_drift": round(assessment.distribution_drift, 4),
    }


def trusted_projection():
    global _TRUSTED_PROJECTION_CACHE
    if _TRUSTED_PROJECTION_CACHE is not None:
        return _TRUSTED_PROJECTION_CACHE
    with _TRUSTED_PROJECTION_LOCK:
        if _TRUSTED_PROJECTION_CACHE is not None:
            return _TRUSTED_PROJECTION_CACHE
        rows = load_manifest("clean_subset")
        records = [blind_record_from_row(row) for row in rows]
        raw_embeddings = extract_embeddings(records, IP102_ROOT, EMBEDDING_CACHE, CLIP_MODEL_CACHE)
        _TRUSTED_PROJECTION_CACHE = fit_trusted_projection(records, raw_embeddings)
        return _TRUSTED_PROJECTION_CACHE


def semantic_assessment(name: str):
    cached = _SEMANTIC_ASSESSMENT_CACHE.get(name)
    if cached is not None:
        return cached
    with _SEMANTIC_ASSESSMENT_LOCK:
        cached = _SEMANTIC_ASSESSMENT_CACHE.get(name)
        if cached is not None:
            return cached
        rows = load_manifest(name)
        records = [blind_record_from_row(row) for row in rows]
        embeddings = extract_embeddings(records, IP102_ROOT, EMBEDDING_CACHE, CLIP_MODEL_CACHE)
        embeddings = {**embeddings, **trusted_projection()}
        cached = assess_semantic(records, embeddings)
        _SEMANTIC_ASSESSMENT_CACHE[name] = cached
        return cached


def semantic_result_by_sample_id(name: str, sample_id: str) -> SemanticSampleResult | dict | None:
    cached = semantic_sample_results().get(name, {}).get(sample_id)
    if cached is not None:
        return cached
    for result in semantic_assessment(name).results:
        if result.sample_id == sample_id:
            return result
    return None


@lru_cache(maxsize=1)
def semantic_summary_document() -> dict:
    if not SEMANTIC_SUMMARY_FILE.is_file():
        return {}
    return json.loads(SEMANTIC_SUMMARY_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def semantic_offline_metrics() -> dict[str, dict]:
    return {
        entry["dataset"]: entry
        for entry in semantic_summary_document().get("datasets", [])
    }


@lru_cache(maxsize=1)
def semantic_sample_results() -> dict[str, dict[str, dict]]:
    if not SEMANTIC_SAMPLE_RESULTS_FILE.is_file():
        return {}
    payload = json.loads(SEMANTIC_SAMPLE_RESULTS_FILE.read_text(encoding="utf-8"))
    if payload.get("detector", {}).get("config_hash") != detector_metadata()["config_hash"]:
        return {}
    return payload.get("datasets", {})


def semantic_payload(name: str) -> dict:
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset: {name}")
    document = semantic_summary_document()
    offline = semantic_offline_metrics().get(name)
    if (
        offline is not None
        and document.get("detector", {}).get("config_hash") == detector_metadata()["config_hash"]
        and offline.get("mean_risk_score") is not None
    ):
        return {
            "dataset": name,
            "detector": document["detector"],
            "decision_counts": offline["decision_counts"],
            "mean_risk_score": offline["mean_risk_score"],
            "samples": offline["samples"],
            "source": "precomputed",
            "offline_evaluation": {
                "precision": offline.get("precision"),
                "recall": offline.get("recall"),
                "f1": offline.get("f1"),
                "clean_false_positive_rate": offline.get("clean_false_positive_rate"),
                "roc_auc": offline.get("roc_auc"),
            },
        }

    assessment = semantic_assessment(name)
    scores = [result.risk_score for result in assessment.results]
    payload = {
        "dataset": name,
        "detector": detector_metadata(),
        "decision_counts": assessment.decision_counts,
        "mean_risk_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "samples": len(assessment.results),
    }
    offline = semantic_offline_metrics().get(name)
    if offline is not None:
        payload["offline_evaluation"] = {
            "precision": offline.get("precision"),
            "recall": offline.get("recall"),
            "f1": offline.get("f1"),
            "clean_false_positive_rate": offline.get("clean_false_positive_rate"),
            "roc_auc": offline.get("roc_auc"),
        }
    return payload


def semantic_sample_payload(result: SemanticSampleResult | dict | None) -> dict | None:
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    return {
        "decision": result.decision,
        "risk_score": result.risk_score,
        "reasons": list(result.reasons),
        "neighbor_label_agreement": result.neighbor_label_agreement,
        "classifier_confidence": result.classifier_confidence,
        "centroid_distance_z": result.centroid_distance_z,
        "neighbors": [
            {
                "sample_id": neighbor.sample_id,
                "assigned_label": neighbor.assigned_label,
                "distance": round(neighbor.distance, 4),
            }
            for neighbor in result.neighbors
        ],
    }


class PoisoningRequestHandler(BaseHTTPRequestHandler):
    server_version = "S6PoisoningLocal/1.0"

    def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_FILE.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/summary":
            try:
                self._send_json([assessment_payload(name) for name in DATASETS])
            except (OSError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/semantic":
            try:
                name = parse_qs(parsed.query).get("dataset", ["clean_subset"])[0]
                self._send_json(semantic_payload(name))
            except (OSError, ValueError, KeyError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/sample":
            try:
                name = parse_qs(parsed.query).get("dataset", ["clean_subset"])[0]
                rows = load_manifest(name)
                trusted = {row["sample_id"]: row for row in load_manifest("clean_subset")}
                changed = [
                    row
                    for row in rows
                    if row["sample_id"] in trusted
                    and (
                        row["assigned_label"] != trusted[row["sample_id"]]["assigned_label"]
                        or row["sha256"] != trusted[row["sample_id"]]["sha256"]
                    )
                ]
                row = random.choice(changed or rows)
                trusted_row = trusted[row["sample_id"]]
                names = class_names()
                self._send_json(
                    {
                        "dataset": name,
                        "sample_id": row["sample_id"],
                        "image_url": f"/api/image?sample_id={quote(row['sample_id'], safe='')}",
                        "original_label": trusted_row["assigned_label"],
                        "original_name": names.get(trusted_row["assigned_label"], "unknown"),
                        "assigned_label": row["assigned_label"],
                        "assigned_name": names.get(row["assigned_label"], "unknown"),
                        "label_changed": row["assigned_label"] != trusted_row["assigned_label"],
                        "hash_changed": row["sha256"] != trusted_row["sha256"],
                        "sha256": row["sha256"],
                        "semantic": semantic_sample_payload(
                            semantic_result_by_sample_id(name, row["sample_id"])
                        ),
                    }
                )
            except (OSError, ValueError, KeyError, IndexError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/image":
            try:
                sample_id = parse_qs(parsed.query).get("sample_id", [""])[0]
                allowed_ids = {row["sample_id"] for row in load_manifest("clean_subset")}
                if sample_id not in allowed_ids:
                    raise ValueError("Image is not part of the trusted experiment subset")
                image_path = (IP102_ROOT / Path(sample_id)).resolve()
                if not image_path.is_relative_to(IP102_ROOT.resolve()) or not image_path.is_file():
                    raise ValueError("Invalid image path")
                body = image_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
            except (OSError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local IP102 integrity application.")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not INDEX_FILE.is_file():
        raise FileNotFoundError(f"Frontend not found: {INDEX_FILE}")
    if not TRUSTED_MANIFEST.is_file():
        raise FileNotFoundError(
            "Generate the experiment manifests with prepare_ip102_poisoning.py first"
        )
    if not EMBEDDING_CACHE.is_file():
        print(
            "Semantic embedding cache not found; the first /api/semantic or /api/sample "
            "request will compute it with CLIP ViT-B/32 on CPU (slow, one-time)."
        )

    server = ThreadingHTTPServer((HOST, args.port), PoisoningRequestHandler)
    url = f"http://{HOST}:{args.port}"
    print(f"S6 IP102 integrity + semantic detector running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping S6 IP102 integrity detector.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
