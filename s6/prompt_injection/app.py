"""Run the S6 prompt-injection detector as a local browser application."""

from __future__ import annotations

import argparse
import json
import random
import threading
import webbrowser
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from detector import (
    BLOCK_THRESHOLD,
    REVIEW_THRESHOLD,
    detect_prompt_injection,
    detector_metadata,
)
from semantic_detector import (
    assess_task_consistency,
    combine_hybrid,
    extract_embeddings,
    texts_requiring_embeddings,
)
from semantic_detector import detector_metadata as semantic_detector_metadata
from confused_deputy_scenarios import SCENARIOS
from tool_policy import TOOL_REGISTRY, ToolCall, append_audit_record, evaluate_tool_call
from tool_policy import policy_metadata as tool_policy_metadata


HOST = "127.0.0.1"
PORT = 8765
MAX_REQUEST_BYTES = 100_000
APP_DIR = Path(__file__).resolve().parent
INDEX_FILE = APP_DIR / "web" / "index.html"
PROJECT_ROOT = APP_DIR.parents[1]
GENERATED_DIR = PROJECT_ROOT / "data" / "bipia" / "generated"
SPLITS_DIR = PROJECT_ROOT / "data" / "bipia" / "splits"
RESULTS_DIR = PROJECT_ROOT / "results" / "bipia"
SEMANTIC_EMBEDDING_CACHE = PROJECT_ROOT / "data" / "bipia" / "semantic_embedding_cache.npz"
MINILM_CACHE_DIR = PROJECT_ROOT / "external" / "minilm_cache"
TOOL_POLICY_AUDIT_LOG = RESULTS_DIR / "tool_policy_audit.jsonl"

SPLIT_SOURCES = {
    "development": "train",
    "unseen_test": "test",
}
SUPPORTED_ENCODINGS = ("plain", "stealth")


@lru_cache(maxsize=4)
def load_examples(
    split: str = "unseen_test", encoding: str = "plain"
) -> tuple[dict, ...]:
    if split not in SPLIT_SOURCES or encoding not in SUPPORTED_ENCODINGS:
        raise ValueError("Unsupported example split or encoding")
    source_split = SPLIT_SOURCES[split]
    example_file = GENERATED_DIR / f"email_{source_split}_{encoding}.jsonl"
    manifest_file = SPLITS_DIR / f"attack_{split}.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    allowed_names = {attack["attack_name"] for attack in manifest["attacks"]}
    examples: list[dict] = []
    with example_file.open("r", encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            if record.get("attack_name") not in allowed_names:
                continue
            examples.append(
                {
                    "text": record["context"],
                    "question": record.get("question", ""),
                    "attack_name": record.get("attack_name", ""),
                    "position": record.get("position", ""),
                    "split": split,
                    "encoding": encoding,
                }
            )
    if not examples:
        raise ValueError(f"The BIPIA example dataset is empty: {split}/{encoding}")
    return tuple(examples)


def load_status() -> dict:
    """Return compact P1 experiment metadata for the local dashboard."""
    metadata = detector_metadata()
    split_status: dict[str, dict] = {}
    for split in SPLIT_SOURCES:
        manifest_file = SPLITS_DIR / f"attack_{split}.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        split_status[split] = {
            "categories": len(manifest["categories"]),
            "attack_variants": len(manifest["attacks"]),
        }

    evaluations: dict[str, dict] = {}
    historical_warning = ""
    for encoding in SUPPORTED_ENCODINGS:
        summary_file = RESULTS_DIR / f"email_p1_{encoding}_summary.json"
        if not summary_file.is_file():
            continue
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        historical_warning = str(summary.get("historical_exposure_warning", ""))
        evaluations[encoding] = {
            "matches_current_detector": all(
                summary.get(key) == metadata[key]
                for key in ("detector", "version", "config_hash")
            ),
            "splits": {
                split: {
                    "attacked_samples": metrics["attacked_samples"],
                    "clean_samples": metrics["clean_samples"],
                    "attack_detection_rate": metrics["attack_detection_rate"],
                    "false_positive_rate": metrics["false_positive_rate"],
                    "precision": metrics["precision"],
                    "f1": metrics["f1"],
                    "median_latency_ms": metrics["latency"]["all"]["median_ms"],
                    "p95_latency_ms": metrics["latency"]["all"]["p95_ms"],
                }
                for split, metrics in summary["splits"].items()
            },
        }

    p2_evaluations: dict[str, dict] = {}
    for encoding in SUPPORTED_ENCODINGS:
        summary_file = RESULTS_DIR / f"email_p2_{encoding}_summary.json"
        if not summary_file.is_file():
            continue
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        p2_evaluations[encoding] = {
            "splits": {
                split: {
                    system: {
                        "attacked_samples": systems[system]["attacked_samples"],
                        "attack_detection_rate": systems[system]["attack_detection_rate"],
                        "false_positive_rate": systems[system]["false_positive_rate"],
                        "f1": systems[system]["f1"],
                    }
                    for system in ("rule", "semantic", "hybrid")
                }
                for split, systems in summary["splits"].items()
            },
        }

    tool_policy_summary_file = RESULTS_DIR / "tool_policy_summary.json"
    tool_policy_evaluation: dict = {}
    if tool_policy_summary_file.is_file():
        tool_policy_summary = json.loads(tool_policy_summary_file.read_text(encoding="utf-8"))
        tool_policy_evaluation = {
            "scenario_count": tool_policy_summary.get("scenario_count", 0),
            "decisions": tool_policy_summary.get("decisions", {}),
            "harm_containment": tool_policy_summary.get("harm_containment", {}),
            "friction_cost": tool_policy_summary.get("friction_cost", {}),
        }

    return {
        **metadata,
        "thresholds": {
            "review": REVIEW_THRESHOLD,
            "block": BLOCK_THRESHOLD,
        },
        "split_status": split_status,
        "evaluations": evaluations,
        "historical_exposure_warning": historical_warning,
        "semantic_detector": semantic_detector_metadata(),
        "p2_evaluations": p2_evaluations,
        "tool_policy": {
            "detector": tool_policy_metadata(),
            "tool_registry": {
                name: {
                    "permission": entry.permission,
                    "trusted_targets": sorted(entry.trusted_targets),
                }
                for name, entry in TOOL_REGISTRY.items()
            },
            "evaluation": tool_policy_evaluation,
        },
    }


class S6RequestHandler(BaseHTTPRequestHandler):
    server_version = "S6Local/1.0"

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/":
            body = INDEX_FILE.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/status":
            try:
                self._send_json(load_status())
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
                self._send_json(
                    {"error": f"Unable to load P1 evaluation status: {error}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if path == "/api/example":
            try:
                query = parse_qs(parsed_url.query)
                split = query.get("split", ["unseen_test"])[0]
                encoding = query.get("encoding", ["plain"])[0]
                if split not in SPLIT_SOURCES or encoding not in SUPPORTED_ENCODINGS:
                    self._send_json(
                        {"error": "Unsupported example split or encoding"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                self._send_json(random.choice(load_examples(split, encoding)))
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as error:
                self._send_json(
                    {"error": f"Unable to load the BIPIA example: {error}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if path == "/api/tool-scenario":
            scenario = random.choice(SCENARIOS)
            self._send_json(
                {
                    "scenario_id": scenario.scenario_id,
                    "description": scenario.description,
                    "content": scenario.content,
                    "tool_name": scenario.tool_call.tool_name,
                    "target": scenario.tool_call.target,
                    "parameters": dict(scenario.tool_call.parameters),
                    "ground_truth": {
                        "triggered_by_untrusted_content": scenario.triggered_by_untrusted_content,
                        "actually_harmful": scenario.actually_harmful,
                    },
                }
            )
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != "/api/detect":
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            return

        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json(
                {"error": "Input must be between 1 and 100,000 bytes"},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            text = payload["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text must be a non-empty string")
            question = payload.get("question", "")
            if not isinstance(question, str):
                raise ValueError("question must be a string")
            tool_name = payload.get("tool_name", "")
            if not isinstance(tool_name, str):
                raise ValueError("tool_name must be a string")
            target = payload.get("target", "")
            if not isinstance(target, str):
                raise ValueError("target must be a string")
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        result = detect_prompt_injection(text)
        metadata = detector_metadata()
        response: dict = {
            "decision": result.decision,
            "score": result.score,
            "reasons": list(result.reasons),
            **metadata,
            "highlights": [
                {"start": highlight.start, "end": highlight.end, "label": highlight.label}
                for highlight in result.highlights
            ],
        }

        if question.strip():
            texts = texts_requiring_embeddings(question, text)
            embeddings = extract_embeddings(texts, SEMANTIC_EMBEDDING_CACHE, MINILM_CACHE_DIR)
            semantic = assess_task_consistency(question, text, embeddings)
            hybrid_decision, hybrid_reasons = combine_hybrid(
                result.decision, result.reasons, semantic
            )
            response["semantic_detector"] = semantic_detector_metadata()
            response["semantic"] = {
                "decision": semantic.decision,
                "score": semantic.score,
                "reasons": list(semantic.reasons),
                "highlights": [
                    {"start": highlight.start, "end": highlight.end, "label": highlight.label}
                    for highlight in semantic.highlights
                ],
            }
            response["hybrid"] = {
                "decision": hybrid_decision,
                "reasons": list(hybrid_reasons),
            }

        if tool_name.strip():
            tool_call = ToolCall(tool_name=tool_name.strip(), target=target.strip(), parameters={})
            policy_result = evaluate_tool_call(tool_call, result.decision)
            entry = TOOL_REGISTRY.get(tool_name.strip())
            response["tool_policy"] = {
                "detector": tool_policy_metadata(),
                "decision": policy_result.decision,
                "reasons": list(policy_result.reasons),
                "permission": entry.permission if entry else None,
            }
            append_audit_record(TOOL_POLICY_AUDIT_LOG, tool_call, result.decision, policy_result)

        self._send_json(response)

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local S6 detector application.")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not INDEX_FILE.is_file():
        raise FileNotFoundError(f"Frontend not found: {INDEX_FILE}")

    server = ThreadingHTTPServer((HOST, args.port), S6RequestHandler)
    url = f"http://{HOST}:{args.port}"
    print(f"S6 detector running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping S6 detector.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
