"""Reproduce small-head training, independently reconstruct scores and repeat NLI."""
from pathlib import Path
import numpy as np
import torch
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.authorization_relation_training import fit_mlp
from s6.prompt_injection.authorization_relation_data import validate
from s6.prompt_injection.verify_authorization_calibration_v1 import verify_metrics, choose_threshold
from s6.prompt_injection.nli_authorization import FrozenNLI

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/bipia/authorization_relation_v1"


def reconstruct(head: dict, features: dict) -> np.ndarray:
    """Independent forward calculation, not the experiment's scoring function."""
    if head["kind"] == "raw_nli":
        return features["nli"][:, 0]
    matrix = features[head["feature"]]
    if head["kind"] == "linear":
        return expit(matrix @ np.asarray(head["coef"])[0] + head["intercept"][0])
    weights = head["weights"]
    hidden = np.tanh(matrix @ np.asarray(weights["0.weight"]).T + np.asarray(weights["0.bias"]))
    return expit((hidden @ np.asarray(weights["2.weight"]).T + np.asarray(weights["2.bias"])).reshape(-1))


def reproduce_training(heads: dict, train_rows: list[dict], cal_rows: list[dict]) -> dict:
    """Repeat deterministic training; refit is an audit, not a new candidate search."""
    errors = {}
    with np.load(RUN / "train_features.npz", allow_pickle=False) as train:
        with np.load(RUN / "calibration_features.npz", allow_pickle=False) as cal:
            for name, head in heads.items():
                if head["kind"] == "raw_nli":
                    continue
                if head["kind"] == "mlp":
                    repeated = fit_mlp(train["joint"], train_rows, head["seed"], head["paired"])
                    error = max(float(np.abs(np.array(values) - repeated["weights"][key]).max())
                                for key, values in head["weights"].items())
                else:
                    model = LogisticRegression(C=1., solver="liblinear", class_weight="balanced", random_state=2026, max_iter=2000)
                    model.fit(train[head["feature"]], [r["label"] for r in train_rows])
                    error = max(float(np.abs(model.coef_ - head["coef"]).max()),
                                float(np.abs(model.intercept_ - head["intercept"]).max()))
                if error > 1e-12:
                    raise ValueError(f"Training replay failed: {name}")
                errors[name] = error
                threshold = choose_threshold([r["label"] for r in cal_rows], reconstruct(head, cal))
                if threshold != head["threshold"]:
                    raise ValueError("Calibration threshold mismatch")
                print(f"Reproduced {name}", flush=True)
    return errors


def verify_partition(name: str, rows: list[dict], heads: dict, summary: dict, nli: FrozenNLI) -> dict:
    """Recount metrics and check exact 50% single-side target accuracy."""
    coverage = read_json(RUN / f"{name}_coverage.json")
    for record in coverage["minilm"]:
        for field in ("task", "content"):
            item = record[field]
            if item["dropped_tokens"] or item["input_tokens"] != item["covered_tokens"]:
                raise ValueError("MiniLM coverage failure")
    predictions = read_json(RUN / f"{name}_predictions.json")
    max_error = 0.
    with np.load(RUN / f"{name}_features.npz", allow_pickle=False) as features:
        for offset, mode in ((0, "raw_contradiction"), (3, "conflict_hypothesis")):
            _, repeated = nli.score(rows, mode)
            prior = [r for r in coverage["nli"] if r["mode"] == mode]
            if repeated != prior or any(r["dropped_tokens"] for r in prior):
                raise ValueError("NLI coverage or repeated inference mismatch")
            if not np.array_equal(features["nli"][:, offset:offset + 3], [r["nli_probabilities"] for r in prior]):
                raise ValueError("NLI feature mismatch")
        for arm, head in heads.items():
            values = reconstruct(head, features)
            stored = predictions[arm]
            quartets = {}
            for row, prediction, value in zip(rows, stored, values, strict=True):
                if (row["id"] != prediction["id"] or row["label"] != prediction["label"]
                        or bool(value >= head["threshold"]) != prediction["flag"]):
                    raise ValueError("Prediction identity or flag mismatch")
                max_error = max(max_error, abs(float(value) - prediction["score"]))
                if row.get("quartet_id"):
                    quartets.setdefault(row["quartet_id"], []).append(prediction["flag"] == row["label"])
            verify_metrics(stored, summary[arm])
            expected = {"count": len(quartets), "all_correct": sum(all(v) for v in quartets.values())}
            if expected != summary[arm]["quartets"]:
                raise ValueError("Quartet count mismatch")
        if name in ("train", "calibration", "test"):
            for arm in ("linear_content", "linear_task_only"):
                if summary[arm]["by_kind"]["target"]["accuracy"] != .5:
                    raise ValueError("Single-side shortcut or broken quartet")
    if max_error > 1e-12:
        raise ValueError("Score replay mismatch")
    return {"predictions": len(rows) * len(heads), "max_score_error": max_error,
            "nli_repeated": len(coverage["nli"]),
            "max_nli_tokens": max(r["input_tokens_with_special"] for r in coverage["nli"])}


def main() -> None:
    torch.set_num_threads(4)
    protocol = read_json(RUN / "protocol.json")
    for path, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / path, digest)
    data_path = ROOT / "data/bipia/authorization_relation_v1/samples.json"
    require_hash(data_path, protocol["data_sha256"])
    require_hash(RUN / "heads.json", read_json(RUN / "integrity.json")["heads_sha256"])
    rows = read_json(data_path)
    audit = validate(rows)
    partitions = {s: [r for r in rows if r["split"] == s] for s in ("train", "calibration", "test")}
    partitions["previous240"] = read_json(ROOT / "data/bipia/authorization_calibration_v1/samples.json")
    partitions["reviewed60"] = [r for r in read_json(ROOT / "data/bipia/authorization_probe_v1/samples.json")
                                if r["split"] == "synthetic_diagnostic"]
    heads, summary = read_json(RUN / "heads.json"), read_json(RUN / "summary.json")
    bound = {str(p.relative_to(ROOT)): file_sha256(p) for p in RUN.iterdir() if p.is_file()}
    with new_run(RUN / "verification", {"code_sha256": file_sha256(Path(__file__)), "artifacts_sha256": bound}):
        training = reproduce_training(heads, partitions["train"], partitions["calibration"])
        nli = FrozenNLI(ROOT / "external/nli_authorization_v1")
        results = {name: verify_partition(name, subset, heads, summary[name], nli) for name, subset in partitions.items()}
        for path, digest in {**bound, **protocol["protected_sha256"]}.items():
            require_hash(ROOT / path, digest)
        write_json(RUN / "verification/result.json", {"audit": audit, "training_max_errors": training, "partitions": results})
    print("Independent verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
