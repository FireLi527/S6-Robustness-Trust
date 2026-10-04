"""Independent coefficient refit, prediction recount and frozen-NLI replay."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import torch
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.nli_authorization import FrozenNLI

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/bipia/authorization_calibration_v1"


def recount(rows: list[dict]) -> dict:
    """Recount without the experiment's metrics helpers."""
    tp = sum(r["label"] == 1 and r["flag"] for r in rows)
    fp = sum(r["label"] == 0 and r["flag"] for r in rows)
    fn = sum(r["label"] == 1 and not r["flag"] for r in rows)
    tn = sum(r["label"] == 0 and not r["flag"] for r in rows)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "samples": len(rows),
            "accuracy": (tp + tn) / len(rows), "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None, "fpr": fp / (fp + tn) if fp + tn else None}


def verify_metrics(predictions: list[dict], stored: dict) -> None:
    """Also independently reconstruct pairs and every reported subgroup."""
    if any(stored[k] != v for k, v in recount(predictions).items()):
        raise ValueError("Metric mismatch")
    pairs = {}
    for row in predictions:
        if row["pair_id"]:
            pairs.setdefault(row["pair_id"], {})[row["label"]] = row
    both = sum(not p[0]["flag"] and p[1]["flag"] for p in pairs.values())
    ranks = sum(p[1]["score"] > p[0]["score"] + 1e-8 for p in pairs.values())
    ties = sum(abs(p[1]["score"] - p[0]["score"]) <= 1e-8 for p in pairs.values())
    expected = {"pairs": len(pairs), "risk_score_higher": ranks, "score_ties": ties,
                "both_correct": both, "both_correct_rate": both / len(pairs) if pairs else None}
    if stored["pairs"] != expected:
        raise ValueError("Pair mismatch")
    for key, field in (("by_kind", "kind"), ("by_group", "group_id")):
        expected_groups = {value: recount([r for r in predictions if r[field] == value])
                           for value in {r[field] for r in predictions}}
        if stored[key] != expected_groups:
            raise ValueError("Subgroup mismatch")


def choose_threshold(labels: list[int], scores: np.ndarray) -> float:
    """Independent explicit finite-candidate calibration reconstruction."""
    options = []
    for threshold in [np.nextafter(scores.max(), np.inf), *np.unique(scores)]:
        result = recount([{"label": y, "flag": s >= threshold} for y, s in zip(labels, scores, strict=True)])
        if result["fpr"] <= .05:
            options.append((result["recall"], -result["fpr"], float(threshold)))
    return max(options)[2]


def verify_heads(selection: dict, partitions: dict) -> None:
    """Refit only the saved training matrix and reselect only on calibration."""
    with np.load(RUN / "train_features.npz", allow_pickle=False) as train:
        with np.load(RUN / "calibration_features.npz", allow_pickle=False) as cal:
            for head in selection["heads"].values():
                model = LogisticRegression(C=head["C"], solver="liblinear", class_weight="balanced",
                                           random_state=2026, max_iter=2000)
                model.fit(train[head["feature"]], [r["label"] for r in partitions["train"]])
                if not np.allclose(model.coef_, head["coef"], rtol=0, atol=1e-12):
                    raise ValueError("Training coefficient replay mismatch")
                if not np.allclose(model.intercept_, head["intercept"], rtol=0, atol=1e-12):
                    raise ValueError("Training intercept replay mismatch")
                scores = expit(cal[head["feature"]] @ np.array(head["coef"])[0] + head["intercept"][0])
                if choose_threshold([r["label"] for r in partitions["calibration"]], scores) != head["threshold"]:
                    raise ValueError("Calibration threshold mismatch")
            threshold = choose_threshold([r["label"] for r in partitions["calibration"]], cal["nli"][:, 0])
            if threshold != selection["raw_nli_calibrated_threshold"]:
                raise ValueError("NLI calibration mismatch")
    for feature, selected in selection["selected"].items():
        heads = {k: h for k, h in selection["heads"].items() if h["feature"] == feature}
        winner = max(heads, key=lambda k: (heads[k]["calibration_metrics"]["recall"],
                                          -heads[k]["calibration_metrics"]["fpr"], -heads[k]["C"]))
        if winner != selected:
            raise ValueError("C selection mismatch")


def verify_partition(name: str, rows: list[dict], selection: dict, summary: dict, nli: FrozenNLI) -> dict:
    """Audit coverage and repeat NLI; all predictions reconstructed from weights."""
    coverage = read_json(RUN / f"{name}_coverage.json")
    for record in coverage["minilm"]:
        for field in ("task", "content"):
            entry = record[field]
            if entry["dropped_tokens"] or entry["input_tokens"] != entry["covered_tokens"]:
                raise ValueError("MiniLM coverage gap")
    max_error = 0.
    predictions = read_json(RUN / f"{name}_predictions.json")
    auc, fixed_half = {}, {}
    with np.load(RUN / f"{name}_features.npz", allow_pickle=False) as features:
        for offset, mode in ((0, "raw_contradiction"), (3, "conflict_hypothesis")):
            _, repeated = nli.score(rows, mode)
            expected = [r for r in coverage["nli"] if r["mode"] == mode]
            if repeated != expected or any(r["dropped_tokens"] for r in expected):
                raise ValueError("NLI inference replay mismatch or coverage gap")
            if not np.array_equal(features["nli"][:, offset:offset + 3], [r["nli_probabilities"] for r in expected]):
                raise ValueError("NLI feature mismatch")
        for arm, stored in predictions.items():
            if arm in selection["heads"]:
                head = selection["heads"][arm]
                scores = expit(features[head["feature"]] @ np.array(head["coef"])[0] + head["intercept"][0])
                threshold = head["threshold"]
            else:
                scores = features["nli"][:, 0]
                threshold = selection["raw_nli_fixed_threshold" if arm == "raw_nli_fixed" else "raw_nli_calibrated_threshold"]
            for row, prediction, score in zip(rows, stored, scores, strict=True):
                if (row["id"] != prediction["id"] or row["label"] != prediction["label"]
                        or prediction["flag"] != bool(score >= threshold)):
                    raise ValueError("Prediction mismatch")
                max_error = max(max_error, abs(float(score) - prediction["score"]))
            verify_metrics(stored, summary[arm])
            auc[arm] = float(roc_auc_score([r["label"] for r in rows], scores))
            fixed_half[arm] = recount([{"label": r["label"], "flag": bool(s >= .5)} for r, s in zip(rows, scores, strict=True)])
    if max_error > 1e-12:
        raise ValueError("Score replay mismatch")
    return {"rows": len(rows), "predictions": sum(map(len, predictions.values())), "max_score_error": max_error,
            "auc_diagnostic_only": auc, "fixed_0_5_diagnostic_only": fixed_half,
            "nli_repeated_rows": len(coverage["nli"]), "max_nli_tokens": max(r["input_tokens_with_special"] for r in coverage["nli"])}


def main() -> None:
    torch.set_num_threads(4)
    protocol = read_json(RUN / "protocol.json")
    for path, digest in protocol["protected_sha256"].items():
        require_hash(ROOT / path, digest)
    data_path = ROOT / "data/bipia/authorization_calibration_v1/samples.json"
    require_hash(data_path, protocol["samples_sha256"])
    integrity = read_json(RUN / "integrity.json")
    require_hash(RUN / "selection.json", integrity["selection_sha256"])
    rows = read_json(data_path)
    partitions = {split: [r for r in rows if r["split"] == split] for split in ("train", "calibration", "test")}
    partitions["reviewed_diagnostic"] = [r for r in read_json(ROOT / "data/bipia/authorization_probe_v1/samples.json")
                                         if r["split"] == "synthetic_diagnostic"]
    selection, summary = read_json(RUN / "selection.json"), read_json(RUN / "summary.json")
    bound = {str(path.relative_to(ROOT)): file_sha256(path) for path in RUN.iterdir() if path.is_file()}
    with new_run(RUN / "verification", {"code_sha256": file_sha256(Path(__file__)), "artifacts_sha256": bound,
                                        "extra_auc_and_fixed_threshold": "post-hoc diagnostics, not model selection"}):
        verify_heads(selection, partitions)
        nli = FrozenNLI(ROOT / "external/nli_authorization_v1")
        results = {}
        for name, subset in partitions.items():
            results[name] = verify_partition(name, subset, selection, summary[name], nli)
            print(f"Verified {name}: {results[name]['predictions']} predictions", flush=True)
        for path, digest in {**bound, **protocol["protected_sha256"]}.items():
            require_hash(ROOT / path, digest)
        write_json(RUN / "verification/result.json", results)
    print("Independent verification complete", flush=True)


if __name__ == "__main__":
    main()
