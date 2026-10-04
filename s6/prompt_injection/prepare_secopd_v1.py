"""Freeze a strictly reconstructed local-only SecOPD classification development set."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.secopd_data import selected_pairs, pair_groups, grouped_split, small_training_ids


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "external/secopd_source_v1"
    release = read_json(source / "release_stats.json")
    path = source / release["filename"]
    require_hash(path, release["sha256"])
    pairs, mapping = selected_pairs(read_json(path))
    groups, grouping = pair_groups(pairs)
    pairs, splitting = grouped_split(pairs, groups)
    small = small_training_ids(pairs)
    out = root / "data/bipia/secopd_pairs_v1"
    protocol = {"source": read_json(source / "protocol.json"), "source_sha256": file_sha256(path),
                "mapping": mapping, "grouping": grouping, "splitting": splitting, "small_pair_ids": small,
                "label_basis": "0 upstream clean data;1 upstream optimized injection carrier; derived construction labels, not new human review",
                "exposure": "first64 source records forced train if selected; metadata/schema/grouping sees full source, no detector scores before split; test is same-source development holdout, not independent benchmark",
                "code_sha256": {name: file_sha256(root/name) for name in ("s6/prompt_injection/secopd_data.py", "s6/prompt_injection/prepare_secopd_v1.py")}}
    with new_run(out, protocol):
        write_json(out / "pairs.json", pairs)
        write_json(out / "integrity.json", {"pairs_sha256": file_sha256(out / "pairs.json")})
    print(f"Prepared {splitting}; small_pairs={len(small)}", flush=True)


if __name__ == "__main__":
    main()
