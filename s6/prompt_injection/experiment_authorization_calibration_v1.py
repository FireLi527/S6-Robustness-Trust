"""Predeclared synthetic family transfer: L2 controls and frozen-NLI calibration."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import torch
from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import calibrate_threshold
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.authorization_calibration_data import build_rows, validate_rows, similarity_audit
from s6.prompt_injection.authorization_calibration import CS, FEATURES, fit_head, calibrate, select_head, evaluate
from s6.prompt_injection.cross_source_training import encode_records, head_scores
from s6.prompt_injection.nli_authorization import FrozenNLI

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/authorization_calibration_v1"
DATA = ROOT / "data/bipia/authorization_calibration_v1"
CODE = ("authorization_calibration_data.py", "authorization_calibration.py",
        "experiment_authorization_calibration_v1.py")


def extract(encoder: LocalTextEncoder, nli: FrozenNLI, rows: list[dict], name: str) -> dict:
    """Frozen complete-input features; record both encoders' coverage."""
    features, coverage = encode_records(encoder, rows, name)
    features["task_only"] = features["joint"][:, :features["content"].shape[1]]
    probabilities, details = [], []
    for mode in ("raw_contradiction", "conflict_hypothesis"):
        _, records = nli.score(rows, mode)
        probabilities.append(np.array([r["nli_probabilities"] for r in records]))
        details.extend(records)
        print(f"{name}: NLI {mode} complete", flush=True)
    features["nli"] = np.concatenate(probabilities, axis=1)
    write_json(OUT / f"{name}_coverage.json", {"minilm": coverage, "nli": details})
    atomic_binary(OUT / f"{name}_features.npz", lambda stream: np.savez_compressed(stream, **features))
    return features


def select_models(training: dict, validation: dict, train_rows: list[dict], cal_rows: list[dict]) -> dict:
    """Complete selection before exposing held-out features or labels to fitting."""
    heads, selected = {}, {}
    for feature in FEATURES:
        candidates = {}
        for c in CS:
            name = f"{feature}_C{c:g}"
            head = fit_head(training[feature], train_rows, c)
            candidates[name] = {**calibrate(head, validation[feature], cal_rows), "feature": feature}
        heads.update(candidates)
        selected[feature] = select_head(candidates)
    threshold, metrics = calibrate_threshold(np.array([r["label"] for r in cal_rows]), validation["nli"][:, 0], .05)
    return {"heads": heads, "selected": selected, "raw_nli_fixed_threshold": .5,
            "raw_nli_calibrated_threshold": threshold, "raw_nli_calibration_metrics": metrics,
            "selection_source": "calibration only; test and reviewed diagnostics never used"}


def score_partition(rows: list[dict], features: dict, selection: dict, name: str) -> dict:
    """Report every predefined arm; never promote using held-out outcomes."""
    scores = {key: (head_scores(head, features[head["feature"]]), head["threshold"])
              for key, head in selection["heads"].items()}
    scores["raw_nli_fixed"] = (features["nli"][:, 0], selection["raw_nli_fixed_threshold"])
    scores["raw_nli_calibrated"] = (features["nli"][:, 0], selection["raw_nli_calibrated_threshold"])
    summary, predictions = {}, {}
    for key, (values, threshold) in scores.items():
        summary[key], predictions[key] = evaluate(rows, values, threshold)
    write_json(OUT / f"{name}_predictions.json", predictions)
    return summary


def protected_inputs() -> dict:
    """Inherit prior protection, and bind the reviewed diagnostic and new code."""
    old = read_json(ROOT / "results/bipia/authorization_probe_v1/protocol.json")
    protected = {**old["protected_sha256"], **old["code_sha256"]}
    protected["data/bipia/authorization_probe_v1/samples.json"] = old["samples_sha256"]
    for name in (*CODE, "authorization_probe.py", "nli_authorization.py", "cross_source_training.py"):
        path = f"s6/prompt_injection/{name}"
        digest = file_sha256(ROOT / path)
        if path in protected and protected[path] != digest:
            raise ValueError(f"Frozen code changed: {path}")
        protected[path] = digest
    for name in ("batch_01_ZH.md", "batch_02_ZH.md", "batch_03_ZH.md", "summary_ZH.md"):
        path = f"results/bipia/authorization_review_v1/{name}"
        protected[path] = file_sha256(ROOT / path)
    spec = "s6/prompt_injection/AUTHORIZATION_CALIBRATION_V1_ZH.md"
    protected[spec] = file_sha256(ROOT / spec)
    for path, digest in protected.items():
        require_hash(ROOT / path, digest)
    return protected


def main() -> None:
    torch.set_num_threads(4)
    np.random.seed(2026)
    protected = protected_inputs()
    rows = build_rows()
    old = [r for r in read_json(ROOT / "data/bipia/authorization_probe_v1/samples.json")
           if r["split"] == "synthetic_diagnostic"]
    if {r["content"] for r in rows} & {r["content"] for r in old}:
        raise ValueError("Reviewed body reused")
    audit = similarity_audit(rows, old)
    with new_run(DATA, {"protected_sha256": protected, "counts": validate_rows(rows),
                        "similarity_audit": audit,
                        "notice": "New programmatic English labels, NOT human-reviewed. Old60 diagnostic only."}):
        write_json(DATA / "samples.json", rows)
    snapshot = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    encoder = LocalTextEncoder(snapshot, ROOT / "external/secopd_embedding_cache_v1", EncodingConfig())
    nli = FrozenNLI(ROOT / "external/nli_authorization_v1")
    protocol = {"protected_sha256": protected, "samples_sha256": file_sha256(DATA / "samples.json"),
                "similarity_audit": audit,
                "encoder": encoder.metadata, "nli": nli.metadata, "C_grid": CS, "features": FEATURES,
                "seed": 2026, "penalty": "l2", "solver": "liblinear", "class_weight": "balanced",
                "scaling": "none; frozen normalized MiniLM and six raw NLI probabilities",
                "calibration": "max recall subject to pooled FPR<=0.05; tie lower FPR, higher threshold",
                "C_selection": "calibration recall, lower FPR, smaller C; separate selection per feature",
                "primary": "selected joint vs joint C=1; raw NLI calibrated vs fixed 0.5 on new task families",
                "controls": "content-only, task-only, learned six-probability NLI head; report all C without test selection",
                "limitations": "240 unreviewed synthetic rows; 8 task families per split and split-specific templates; small calibration; no claim of natural generalization, causal overfitting diagnosis or NLI fine-tuning",
                "decision": "No deployment. No new tuning after held-out results. Old60 only post-selection diagnostics."}
    with new_run(OUT, protocol):
        subsets = {split: [r for r in rows if r["split"] == split] for split in ("train", "calibration", "test")}
        training = extract(encoder, nli, subsets["train"], "train")
        validation = extract(encoder, nli, subsets["calibration"], "calibration")
        selection = select_models(training, validation, subsets["train"], subsets["calibration"])
        write_json(OUT / "selection.json", selection)
        selection_digest = file_sha256(OUT / "selection.json")
        print(f"Selection frozen before test: {selection['selected']}", flush=True)
        summary = {"train": score_partition(subsets["train"], training, selection, "train"),
                   "calibration": score_partition(subsets["calibration"], validation, selection, "calibration")}
        for name, subset in (("test", subsets["test"]), ("reviewed_diagnostic", old)):
            features = extract(encoder, nli, subset, name)
            summary[name] = score_partition(subset, features, selection, name)
        write_json(OUT / "summary.json", summary)
        for path, digest in protected.items():
            require_hash(ROOT / path, digest)
        require_hash(DATA / "samples.json", protocol["samples_sha256"])
        require_hash(OUT / "selection.json", selection_digest)
        write_json(OUT / "integrity.json", {"protected_files": len(protected), "selection_sha256": selection_digest,
                                           "data_sha256": protocol["samples_sha256"], "frozen_checks": "passed"})
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
