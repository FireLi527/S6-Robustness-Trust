"""Create immutable risk-weighted fruit-fly manifests from grouped_defense_v1.

All candidate images are retained.  The frozen out-of-fold detector risk only
changes the supervised loss weight: max(floor, 1-risk).  No test image or test
metric is used to construct these manifests.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/fruitfly_poisoning/manifests"
PREDICTIONS = ROOT / "results/fruitfly_poisoning/grouped_defense_v1/candidate_predictions.json"
OUT = ROOT / "data/fruitfly_poisoning/weighted_v2"
DATASETS = ("clean_subset", "label_flip_05", "label_flip_10", "targeted_0_to_1")
FLOORS = (.25, .50)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise RuntimeError("weighted_v2 already exists; do not overwrite frozen manifests")
    payload = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True)
    protocol = {
        "status": "FROZEN", "method": "retain all samples; weight=max(floor,1-risk)",
        "risk_source": "grouped_defense_v1 specimen-disjoint OOF candidate-label risk",
        "floors": list(FLOORS), "candidate_predictions_sha256": sha(PREDICTIONS),
        "hidden_truth_used": False, "test_metrics_used": False, "variants": {},
    }
    for dataset in DATASETS:
        source = SOURCE / f"{dataset}.csv"
        rows = list(csv.DictReader(source.open(encoding="utf-8-sig", newline="")))
        predictions = payload["datasets"][dataset]
        if {row["sample_id"] for row in rows} != set(predictions):
            raise ValueError(f"Prediction coverage mismatch: {dataset}")
        for floor in FLOORS:
            name = f"{dataset}__weighted_{int(floor * 100):02d}"
            destination = OUT / f"{name}.csv"
            weighted = []
            for row in rows:
                risk = float(predictions[row["sample_id"]]["risk_score"])
                weighted.append({**row, "risk_score": f"{risk:.12f}",
                                 "sample_weight": f"{max(floor, 1.0-risk):.12f}"})
            with destination.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(weighted[0]))
                writer.writeheader(); writer.writerows(weighted)
            protocol["variants"][name] = {
                "source_manifest_sha256": sha(source), "manifest_sha256": sha(destination),
                "samples": len(weighted), "mean_weight": sum(float(r["sample_weight"]) for r in weighted)/len(weighted),
            }
    (OUT / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(protocol, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
