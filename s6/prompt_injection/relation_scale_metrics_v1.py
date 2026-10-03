"""Complete, deduplicated development metrics; never tool authorization."""
ARMS = ("base_zero", "base_fewshot", "small_8", "medium_16", "large_28")


def jobs(rows: list) -> list:
    """One deterministic inference per distinct side/text; reject target conflict."""
    seen = {}
    for row in rows:
        if row["split"] != "validation":
            raise ValueError("Evaluation must use validation only")
        for side in ("task", "content"):
            key = (side, row["inputs"][side])
            if key in seen and seen[key][0]["targets"][side] != row["targets"][side]:
                raise ValueError("Conflicting duplicate reference")
            seen.setdefault(key, (row, side))
    return list(seen.values())


def coverage(predictions: list, rows: list, arms: tuple = ARMS) -> None:
    """Missing sides and duplicates must fail, not produce optimistic metrics."""
    expected = {(r["id"], side, arm) for r in rows for side in ("task", "content") for arm in arms}
    keys = [(p["id"], p["side"], p["arm"]) for p in predictions]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Missing, unexpected or duplicate predictions")


def aggregate(predictions: list, rows: list) -> dict:
    """Case-weighted and unique-input scores, including invalid outputs."""
    lookup = {r["id"]: r for r in rows}
    unique = {}
    for p in predictions:
        key = (p["side"], lookup[p["id"]]["inputs"][p["side"]])
        if key in unique and any(p[k] != unique[key][k] for k in ("text", "finished", "score")):
            raise ValueError("Inconsistent deterministic duplicate")
        unique[key] = p
    by_id = {r["id"]: [p for p in predictions if p["id"] == r["id"]] for r in rows}
    group_rates = {}
    for group in sorted({r["group_id"] for r in rows}):
        selected = [p for p in unique.values() if lookup[p["id"]]["group_id"] == group]
        group_rates[group] = sum(p["score"]["exact"] for p in selected) / len(selected)
    units = {k: sum(p["score"][k] for p in unique.values()) for k in ("matched", "predicted", "reference")}
    return {"pairs": len(rows), "side_samples": len(predictions),
            "valid": sum(p["score"]["valid"] for p in predictions),
            "exact": sum(p["score"]["exact"] for p in predictions),
            "both_exact": sum(len(ps) == 2 and all(p["score"]["exact"] for p in ps) for ps in by_id.values()),
            "unique_sides": len(unique), "unique_valid": sum(p["score"]["valid"] for p in unique.values()),
            "unique_exact": sum(p["score"]["exact"] for p in unique.values()),
            "unique_unfinished": sum(not p["finished"] for p in unique.values()),
            "by_side": {side: {"n": sum(p["side"] == side for p in unique.values()),
                               "exact": sum(p["side"] == side and p["score"]["exact"] for p in unique.values())}
                        for side in ("task", "content")},
            "strict_units": {**units, "precision": units["matched"] / units["predicted"] if units["predicted"] else None,
                             "recall": units["matched"] / units["reference"] if units["reference"] else None},
            "group_exact_rates": group_rates, "macro_group_exact": sum(group_rates.values()) / len(group_rates)}


def summarize(predictions: list, rows: list) -> dict:
    """No threshold selection, statistical claim or attack metrics."""
    coverage(predictions, rows)
    result = {}
    for arm in ARMS:
        result[arm] = {}
        for variant in ("all", "core", "layout"):
            selected = [r for r in rows if variant == "all" or r["variant"] == variant]
            ids = {r["id"] for r in selected}
            result[arm][variant] = aggregate([p for p in predictions if p["arm"] == arm and p["id"] in ids], selected)
    return result
