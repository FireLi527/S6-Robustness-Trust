"""No-fit NLI pilot on frozen synthetic contrasts and previously reviewed diagnostics."""
from pathlib import Path
import numpy as np
import torch
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.authorization_probe import fixtures, pair_summary
from s6.prompt_injection.nli_authorization import FrozenNLI, MODES, HYPOTHESIS
from s6.prompt_injection.prerequisite_protocol import reviewed_candidates, pair_metrics
from s6.prompt_injection.cross_source_training import encode_records, head_scores

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/authorization_probe_v1"


def scored_rows(rows: list[dict], scores: list[float], threshold: float) -> list[dict]:
    """No raw data copied into prediction files; preserve paired identifiers."""
    if len(rows) != len(scores) or not np.isfinite(scores).all() or not np.isfinite(threshold):
        raise ValueError("Invalid scores or threshold")
    return [{**{k: r[k] for k in ("id", "group_id", "label", "split")},
             "pair_id": r.get("pair_id"), "wording": r.get("wording", "reviewed"),
             "score": float(s), "flag": bool(s >= threshold)} for r, s in zip(rows, scores, strict=True)]


def summarize(rows: list[dict]) -> dict:
    """Report pair sensitivity, quoted controls, and seen diagnostics separately."""
    result = {}
    for name, subset in (("synthetic_pairs", [r for r in rows if r["pair_id"] is not None]),
                         ("quoted_normal", [r for r in rows if r["wording"] == "quoted_normal"]),
                         ("old_reviewed", [r for r in rows if r["split"] == "seen_diagnostic"])):
        metrics = binary_metrics(np.array([r["label"] for r in subset]), np.array([r["flag"] for r in subset]))
        if name == "synthetic_pairs":
            metrics["pairs"] = pair_summary(subset)
            metrics["wording"] = {w: pair_summary([r for r in subset if r["wording"] == w]) for w in ("explicit", "scope")}
        elif name == "old_reviewed":
            metrics["pairs"] = pair_metrics(subset)
        result[name] = metrics
    return result


def main() -> None:
    torch.set_num_threads(4)
    previous = read_json(ROOT / "results/bipia/cross_source_training_v1/protocol.json")
    protected = {**previous["protected_sha256"], **previous["input_sha256"]}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    rows = fixtures() + [{**r, "split": "seen_diagnostic"} for r in reviewed_candidates(ROOT)]
    data_dir = ROOT / "data/bipia/authorization_probe_v1"
    code = ("s6/prompt_injection/authorization_probe.py", "s6/prompt_injection/nli_authorization.py",
            "s6/prompt_injection/experiment_authorization_probe_v1.py")
    with new_run(data_dir, {"code_sha256": {n: file_sha256(ROOT / n) for n in code},
                           "label_notice": "60 new programmatic fixtures (24 opposite-label pairs and12 quoted controls), NOT human reviewed; 12 old human-reviewed rows remain seen diagnostics",
                           "training": "none; labels never used to fit weights or choose threshold"}):
        write_json(data_dir / "samples.json", rows)
    nli = FrozenNLI(ROOT / "external/nli_authorization_v1")
    snapshot = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    encoder = LocalTextEncoder(snapshot, ROOT / "external/secopd_embedding_cache_v1", EncodingConfig())
    head_path = ROOT / "results/bipia/cross_source_training_v1/selection.json"
    heads = read_json(head_path)
    baseline_names = ("legacy_content", "legacy_joint", "mixed_all_content", "mixed_all_joint")
    protocol = {"protected_sha256": protected, "code_sha256": {n: file_sha256(ROOT / n) for n in code},
                "samples_sha256": file_sha256(data_dir / "samples.json"), "heads_sha256": file_sha256(head_path),
                "nli_model": nli.metadata, "baseline_encoder": encoder.metadata,
                "modes": MODES, "hypothesis": HYPOTHESIS, "nli_threshold": .5, "baselines": baseline_names,
                "primary": "conflict_hypothesis pair direction and both-correct versus task_ablated and frozen heads",
                "limits": "unreviewed templated synthetic diagnostic, no finetuning/calibration; old12 seen; different pretrained weights/capacity so not an architecture-only causal ablation",
                "decision": "No deployment. All modes reported. General NLI probabilities are risk proxies, not authorized tool policy."}
    with new_run(OUT, protocol):
        features, coverage = encode_records(encoder, rows, "pilot")
        summary, nli_coverage = {}, []
        for name in baseline_names:
            predictions = scored_rows(rows, head_scores(heads[name], features[heads[name]["feature"]]).tolist(), heads[name]["threshold"])
            summary[name] = summarize(predictions)
            write_json(OUT / f"{name}_predictions.json", predictions)
        for mode in MODES:
            scores, details = nli.score(rows, mode)
            predictions = scored_rows(rows, scores, .5)
            summary[mode] = summarize(predictions)
            nli_coverage.extend(details)
            write_json(OUT / f"{mode}_predictions.json", predictions)
            print(f"Scored {mode}: {summary[mode]}", flush=True)
        write_json(OUT / "summary.json", summary)
        write_json(OUT / "baseline_coverage.json", coverage)
        write_json(OUT / "nli_coverage.json", nli_coverage)
        for name, digest in {**protected, **protocol["code_sha256"]}.items():
            require_hash(ROOT / name, digest)
        require_hash(data_dir / "samples.json", protocol["samples_sha256"])
        require_hash(head_path, protocol["heads_sha256"])
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
