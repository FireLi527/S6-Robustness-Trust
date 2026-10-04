"""Text-only frozen parser feasibility; no training, thresholds or deployment."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.authorization_slots import decide
from s6.prompt_injection.authorization_slots_data import build_rows
from s6.prompt_injection.authorization_slots_evaluation import summarize

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/bipia/authorization_slots_v1"
DATA = ROOT / "data/bipia/authorization_slots_v1"


def main() -> None:
    design = read_json(ROOT / "data/bipia/authorization_slots_v1_design/protocol.json")
    protected = {**read_json(ROOT / "results/bipia/authorization_relation_v1/protocol.json")["protected_sha256"],
                 **design["code_sha256"]}
    paths = ["data/bipia/authorization_relation_v1/samples.json",
             "results/bipia/authorization_relation_v1/heads.json",
             "s6/prompt_injection/authorization_slots_data.py", "s6/prompt_injection/authorization_slots_evaluation.py",
             "s6/prompt_injection/experiment_authorization_slots_v1.py"]
    protected.update({p: file_sha256(ROOT / p) for p in paths})
    for path, digest in protected.items():
        require_hash(ROOT / path, digest)
    rows = build_rows()
    with new_run(DATA, {"protected_sha256": protected, "design": design,
                        "notice": "Post-parser-freeze synthetic fixtures; NOT human-reviewed; contract is not unseen grammar"}):
        write_json(DATA / "samples.json", rows)
    diagnostics = {"seen540": read_json(ROOT / "data/bipia/authorization_relation_v1/samples.json"),
                   "reviewed60": [r for r in read_json(ROOT / "data/bipia/authorization_probe_v1/samples.json")
                                  if r["split"] == "synthetic_diagnostic"]}
    groups = {section: [r for r in rows if r["section"] == section]
              for section in ("grammar_contract", "wording_holdout", "boundary_pressure")}
    protocol = {"protected_sha256": protected, "samples_sha256": file_sha256(DATA / "samples.json"),
                "design": design, "kind": "deterministic text-only extraction with abstention",
                "labels": "programmatic, unknown-label pressure rows excluded from binary denominators",
                "decision": "No training, thresholds, test-time rule updates, deployment or tool authorization"}
    with new_run(OUT, protocol):
        summary = {}
        for name, subset in {**groups, **diagnostics}.items():
            predictions = [{"id": r["id"], **decide(r["task"], r["content"])} for r in subset]
            write_json(OUT / f"{name}_predictions.json", predictions)
            summary[name] = summarize(subset, predictions)
            print(f"{name}: coverage={summary[name]['coverage_all']}, decisions={summary[name]['decisions']}", flush=True)
        write_json(OUT / "summary.json", summary)
        for path, digest in protected.items():
            require_hash(ROOT / path, digest)
        require_hash(DATA / "samples.json", protocol["samples_sha256"])
        write_json(OUT / "integrity.json", {"protected_files": len(protected), "samples_sha256": protocol["samples_sha256"]})
    print(f"Completed: {OUT}", flush=True)


if __name__ == "__main__":
    main()
