"""Active image baseline. Historical IP102 inputs/results remain untouched."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_NAME = "STL-10"
DATA_ROOT = PROJECT_ROOT / "data" / "stl10_poisoning"
IMAGE_ROOT = DATA_ROOT / "images"
RESULTS_ROOT = PROJECT_ROOT / "results" / "stl10_poisoning"
MANIFEST_ROOT = DATA_ROOT / "manifests"
SELECTED_LABELS = tuple(range(10))


def manifest_hashes() -> dict[str, str]:
    import hashlib
    return {path.stem: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(MANIFEST_ROOT.glob("*.csv"))}


def evaluation_matches(payload: dict) -> bool:
    from semantic_detector import detector_metadata
    return (payload.get("detector", {}).get("config_hash") == detector_metadata()["config_hash"]
            and bool(payload.get("manifest_hashes"))
            and payload["manifest_hashes"] == manifest_hashes())
