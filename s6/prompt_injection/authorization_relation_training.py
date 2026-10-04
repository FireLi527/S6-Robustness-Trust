"""Small paired-loss heads on frozen features; no encoder fine-tuning."""
from __future__ import annotations

import numpy as np
import torch
from scipy.special import expit
from s6.engineering.metrics import calibrate_threshold
from s6.prompt_injection.authorization_calibration import fit_head
from s6.prompt_injection.cross_source_training import head_scores

SEEDS = (2026, 2027, 2028)
STEPS = 300


def pair_indices(rows: list[dict]) -> tuple[list[int], list[int]]:
    """Pairs must contain same body and opposite binary labels in train only."""
    groups = {}
    for index, row in enumerate(rows):
        if row["split"] != "train":
            raise ValueError("Non-training pair")
        if row.get("pair_id"):
            groups.setdefault(row["pair_id"], []).append(index)
    safe, risk = [], []
    for indices in groups.values():
        if (len(indices) != 2 or {rows[i]["label"] for i in indices} != {0, 1}
                or len({rows[i]["content"] for i in indices}) != 1):
            raise ValueError("Invalid training pair")
        safe.append(next(i for i in indices if rows[i]["label"] == 0))
        risk.append(next(i for i in indices if rows[i]["label"] == 1))
    if not groups:
        raise ValueError("No training pairs")
    return safe, risk


def paired_penalty(logits: torch.Tensor, safe: list[int], risk: list[int]) -> torch.Tensor:
    """Soft ranking penalty asks risky logits to exceed authorized logits by 0.5."""
    return torch.nn.functional.softplus(.5 + logits[safe] - logits[risk]).mean()


def fit_mlp(features: np.ndarray, rows: list[dict], seed: int, paired: bool) -> dict:
    """Fixed 64-unit MLP, 300 full-batch AdamW steps; no early stop on test."""
    safe, risk = pair_indices(rows)
    if seed not in SEEDS or features.ndim != 2 or len(features) != len(rows) or not np.isfinite(features).all():
        raise ValueError("Invalid MLP inputs")
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    model = torch.nn.Sequential(torch.nn.Linear(features.shape[1], 64), torch.nn.Tanh(), torch.nn.Linear(64, 1))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.001)
    x = torch.tensor(features, dtype=torch.float32)
    y = torch.tensor([r["label"] for r in rows], dtype=torch.float32)
    weights = torch.where(y > 0, len(y) / (2 * y.sum()), len(y) / (2 * (1 - y).sum()))
    trace = []
    for step in range(STEPS):
        optimizer.zero_grad()
        logits = model(x).squeeze(1)
        classification = (torch.nn.functional.binary_cross_entropy_with_logits(logits, y, reduction="none") * weights).mean()
        ranking = paired_penalty(logits, safe, risk)
        loss = classification + (.5 * ranking if paired else 0)
        if not torch.isfinite(loss):
            raise ValueError("Non-finite training loss")
        loss.backward()
        optimizer.step()
        if step in (0, 99, 199, 299):
            trace.append({"step": step + 1, "bce": float(classification.detach()), "ranking": float(ranking.detach())})
    return {"kind": "mlp", "feature": "joint", "seed": seed, "paired": paired, "steps": STEPS,
            "weights": {key: value.detach().numpy().tolist() for key, value in model.state_dict().items()}, "trace": trace}


def scores(head: dict, features: dict[str, np.ndarray]) -> np.ndarray:
    """Inference consumes only text-derived features, never audit-only IDs."""
    if head["kind"] == "raw_nli":
        return features["nli"][:, 0]
    if head["kind"] == "linear":
        return head_scores(head, features[head["feature"]])
    if head["kind"] != "mlp":
        raise ValueError("Unknown head kind")
    w = {k: np.array(v, dtype=np.float64) for k, v in head["weights"].items()}
    x = features[head["feature"]]
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("Invalid feature matrix")
    hidden = np.tanh(x @ w["0.weight"].T + w["0.bias"])
    return expit((hidden @ w["2.weight"].T + w["2.bias"]).reshape(-1))


def fit_all(train: dict, cal: dict, train_rows: list[dict], cal_rows: list[dict], old_threshold: float) -> dict:
    """All 12 heads predefined; select thresholds on calibration, never seeds."""
    if not cal_rows or any(r["split"] != "calibration" for r in cal_rows):
        raise ValueError("Calibration partition required")
    heads = {}
    for feature in ("content", "task_only", "joint", "nli"):
        heads[f"linear_{feature}"] = {**fit_head(train[feature], train_rows, 1.), "kind": "linear", "feature": feature}
    for seed in SEEDS:
        for paired in (False, True):
            name = f"{'paired' if paired else 'bce'}_{seed}"
            heads[name] = fit_mlp(train["joint"], train_rows, seed, paired)
    labels = np.array([r["label"] for r in cal_rows])
    for head in heads.values():
        threshold, metrics = calibrate_threshold(labels, scores(head, cal), .05)
        head.update(threshold=threshold, calibration_metrics=metrics)
    heads["raw_nli_fixed"] = {"kind": "raw_nli", "threshold": .5}
    heads["raw_nli_previous_calibration"] = {"kind": "raw_nli", "threshold": old_threshold}
    return heads
