"""Fixed-protocol target-quartet research; no LLM or encoder fine-tuning."""
from pathlib import Path
import torch
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.text_embeddings import EncodingConfig, LocalTextEncoder
from s6.prompt_injection.authorization_relation_data import build_rows, validate
from s6.prompt_injection.authorization_calibration_data import similarity_audit
from s6.prompt_injection.authorization_relation_training import fit_all, SEEDS, STEPS
from s6.prompt_injection.authorization_relation_run import extract, evaluate_all, seed_summary
from s6.prompt_injection.nli_authorization import FrozenNLI

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/authorization_relation_v1"
DATA = ROOT / "data/bipia/authorization_relation_v1"


def inputs() -> tuple[dict, dict]:
    """Inherit prior immutable inputs and bind this version's code and diagnostics."""
    prior = ROOT / "results/bipia/authorization_calibration_v1"
    protected = read_json(prior / "protocol.json")["protected_sha256"]
    paths = ["data/bipia/authorization_calibration_v1/samples.json",
             "results/bipia/authorization_calibration_v1/selection.json",
             "s6/prompt_injection/AUTHORIZATION_RELATION_V1_ZH.md"]
    paths.extend(f"s6/prompt_injection/{name}" for name in
                 ("authorization_relation_data.py", "authorization_relation_training.py",
                  "authorization_relation_run.py", "experiment_authorization_relation_v1.py"))
    for path in paths:
        protected[path] = file_sha256(ROOT / path)
    for path, digest in protected.items():
        require_hash(ROOT / path, digest)
    old = {"previous240": read_json(ROOT / "data/bipia/authorization_calibration_v1/samples.json"),
           "reviewed60": [r for r in read_json(ROOT / "data/bipia/authorization_probe_v1/samples.json")
                          if r["split"] == "synthetic_diagnostic"]}
    return protected, old


def main() -> None:
    torch.set_num_threads(4)
    protected, old = inputs()
    rows = build_rows()
    audit = {**validate(rows), "similarity": similarity_audit(rows, old["previous240"] + old["reviewed60"])}
    with new_run(DATA, {"audit": audit, "protected_sha256": protected,
                        "notice": "New exact-ID synthetic target quartets; NOT human-reviewed"}):
        write_json(DATA / "samples.json", rows)
    snapshot = ROOT / "external/minilm_cache/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    encoder = LocalTextEncoder(snapshot, ROOT / "external/secopd_embedding_cache_v1", EncodingConfig())
    nli = FrozenNLI(ROOT / "external/nli_authorization_v1")
    old_threshold = read_json(ROOT / "results/bipia/authorization_calibration_v1/selection.json")["raw_nli_calibrated_threshold"]
    protocol = {"protected_sha256": protected, "data_sha256": file_sha256(DATA / "samples.json"),
                "audit": audit, "encoder": encoder.metadata, "nli": nli.metadata, "seeds": SEEDS,
                "mlp": {"hidden": 64, "activation": "tanh", "steps": STEPS, "optimizer": "AdamW",
                        "lr": .001, "weight_decay": .001, "loss": "balanced BCE + optional 0.5*softplus(0.5+safe_logit-risk_logit)",
                        "batch": "full", "device": "cpu", "early_stopping": False},
                "arms": "4 C=1 LR controls, BCE and paired MLP x3 seeds, raw NLI fixed/previous threshold; 12 total",
                "calibration": "new calibration only, pooled FPR<=.05; maximize recall, then lower FPR/higher threshold",
                "primary": "paired versus BCE seed mean on fresh target quartets, including normal quotation FPR",
                "limits": "Literal-ID, programmatic, unreviewed; family/template holdout not external blind natural evaluation. No encoder fine-tuning or production change.",
                "selection": "No seed selection, no test tuning; all heads saved before test and old diagnostics"}
    with new_run(OUT, protocol):
        subsets = {s: [r for r in rows if r["split"] == s] for s in ("train", "calibration", "test")}
        train = extract(encoder, nli, subsets["train"], OUT, "train")
        cal = extract(encoder, nli, subsets["calibration"], OUT, "calibration")
        heads = fit_all(train, cal, subsets["train"], subsets["calibration"], old_threshold)
        write_json(OUT / "heads.json", heads)
        head_hash = file_sha256(OUT / "heads.json")
        print("All 12 heads and thresholds frozen before test", flush=True)
        summary = {"train": evaluate_all(subsets["train"], train, heads, OUT, "train"),
                   "calibration": evaluate_all(subsets["calibration"], cal, heads, OUT, "calibration")}
        for name, subset in {"test": subsets["test"], **old}.items():
            features = extract(encoder, nli, subset, OUT, name)
            summary[name] = evaluate_all(subset, features, heads, OUT, name)
        write_json(OUT / "summary.json", summary)
        write_json(OUT / "seed_summary.json", {name: seed_summary(value) for name, value in summary.items()})
        for path, digest in protected.items():
            require_hash(ROOT / path, digest)
        require_hash(DATA / "samples.json", protocol["data_sha256"])
        require_hash(OUT / "heads.json", head_hash)
        write_json(OUT / "integrity.json", {"protected_files": len(protected), "heads_sha256": head_hash,
                                           "data_sha256": protocol["data_sha256"]})
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
