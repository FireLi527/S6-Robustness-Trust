"""Freeze source-separated data and evaluation boundaries before any model fit."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.aggregation_data import reviewed_pairs
from s6.prompt_injection.prerequisite_protocol import reviewed_candidates
from s6.prompt_injection.secopd_training import expand_pairs
from s6.prompt_injection.cross_source_data import spml_rows, split_spml, external_rows, external_overlap, balanced_group_subset


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    folder = root / "external/cross_source_v1"
    for name, record in read_json(folder / "manifest.json").items():
        require_hash(folder / name, record["sha256"])
    previous = read_json(root / "results/bipia/secopd_training_v1/protocol.json")
    protected = {**previous["protected_sha256"], **previous["input_sha256"]}
    for name, digest in protected.items():
        require_hash(root / name, digest)
    old_protocol = read_json(root / "data/bipia/secopd_pairs_v1/protocol.json")
    old = expand_pairs(read_json(root / "data/bipia/secopd_pairs_v1/pairs.json"), old_protocol["small_pair_ids"])
    old = [{**r, "source": "secopd", "group_id": f'secopd-{r["group_id"]}', "role": "user_task/input_data"} for r in old]
    spml, mapping = spml_rows(folder / "spml/spml_prompt_injection.csv")
    print("Grouping selected SPML and all old SecOPD records", flush=True)
    spml, grouping = split_spml(spml, old)
    external, external_audit = external_rows(folder)
    reviewed = [{**r, "source": "prerequisite" if r["id"].startswith("prereq-v1-") else "reviewed",
                 "split": "seen_diagnostic", "role": "user_task/repository_text"}
                for r in reviewed_pairs(root) + reviewed_candidates(root)]
    excluded = external_overlap(spml + old, external + reviewed)
    evaluation = [r for r in external + reviewed if r["id"] not in excluded]
    development = spml + [r for r in old if r["split"] != "test"]
    matched = {source: balanced_group_subset([r for r in development if r["source"] == source and r["split"] == "train"])
               for source in ("secopd", "spml")}
    protocol = {"purpose": "cross-source training; SPML contextual conflicts are not repository authorization labels",
                "spml_mapping": mapping, "spml_grouping": grouping, "external_mapping": external_audit,
                "external_overlap_excluded": excluded, "matched_training_ids": matched,
                "source_manifest_sha256": file_sha256(folder / "manifest.json"), "protected_sha256": protected,
                "exposure": "SPML first context forced train; source schemas/all metadata inspected; SPML heldout same-source development; InjecAgent related SecFid data previously inspected, new-source transfer diagnostic not untouched benchmark; 48 old reviewed rows seen before; old SecOPD test excluded from scoring and fitting",
                "code_sha256": {p: file_sha256(root / p) for p in ("s6/prompt_injection/cross_source_data.py", "s6/prompt_injection/prepare_cross_source_v1.py")}}
    out = root / "data/bipia/cross_source_v1"
    with new_run(out, protocol):
        write_json(out / "development.json", development)
        write_json(out / "evaluation.json", evaluation)
        write_json(out / "integrity.json", {name: file_sha256(out / name) for name in ("development.json", "evaluation.json")})
    print(f"Prepared SPML splits: {grouping['counts']}; evaluation rows={len(evaluation)}; excluded={len(excluded)}; matched={[len(v) for v in matched.values()]}", flush=True)


if __name__ == "__main__":
    main()
