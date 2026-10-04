"""Develop, then freeze revised prompts before independently authoring new samples."""
import argparse
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.instruction_slot_model import metadata
from s6.prompt_injection.instruction_slot_trial import ARMS, run_trial

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "data/bipia/instruction_slots_v2_design"
DEVELOPMENT = ROOT / "data/bipia/instruction_slots_v1/samples.json"
FRESH = ROOT / "data/bipia/instruction_slots_v2/samples.json"


def protected_files() -> dict:
    """Extend, never rewrite, the earlier experiment's integrity chain."""
    protected = read_json(ROOT / "results/bipia/instruction_slots_v1/protocol.json")["protected_sha256"]
    for path in (DEVELOPMENT, Path(__file__),
                 ROOT / "s6/prompt_injection/instruction_slot_fewshot.py",
                 ROOT / "s6/prompt_injection/instruction_slot_trial.py"):
        protected[str(path.relative_to(ROOT))] = file_sha256(path)
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    return protected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("develop", "freeze", "evaluate"))
    args = parser.parse_args()
    if args.stage == "develop":
        run_trial(ROOT, ROOT / "results/bipia/instruction_slots_v2_development", read_json(DEVELOPMENT),
                  {"protected_sha256": protected_files(), "purpose": "All 32 exposed v1 rows; includes few-shot examples; NOT validation"},
                  ("structured_v2",))
    elif args.stage == "freeze":
        if FRESH.exists():
            raise ValueError("Fresh samples must be authored AFTER prompt freeze")
        development = ROOT / "results/bipia/instruction_slots_v2_development"
        if read_json(development / "status.json")["state"] != "COMPLETE":
            raise ValueError("Development incomplete")
        with new_run(DESIGN, {"protected_sha256": protected_files(), "model": metadata(),
                             "development_summary_sha256": file_sha256(development / "summary.json"),
                             "plan": "32 new programmatic English cases: 16 target, 8 scope, 8 quotation/escape; four NEW operation families and changed phrasing; 16 normal/16 risk. Same rows for three arms. No human review. No holdout prompt changes.",
                             "criteria": "Report coverage, selective accuracy, risk recall, FPR, risky auto-normal and extraction exactness. Improvement requires greater coverage without increased risky auto-normal versus v1 on SAME rows; this is not deployment approval.",
                             "unchanged": "model, generation settings, evidence grounding, comparator, direct prompt; no training"}):
            write_json(DESIGN / "frozen.json", {"ready_for_fresh_data": True})
    else:
        design = read_json(DESIGN / "protocol.json")
        protected = {**design["protected_sha256"], str(FRESH.relative_to(ROOT)): file_sha256(FRESH)}
        rows = read_json(FRESH)
        if len(rows) != 32 or sum(r["label"] for r in rows) != 16 or len({r["id"] for r in rows}) != 32:
            raise ValueError("Holdout size, balance, or IDs invalid")
        run_trial(ROOT, ROOT / "results/bipia/instruction_slots_v2", rows,
                  {"protected_sha256": protected, "design_sha256": file_sha256(DESIGN / "protocol.json"),
                   "label_basis": "programmatic; NOT human-reviewed", "purpose": "Fresh synthetic evaluation; no adaptive prompt changes"}, ARMS)


if __name__ == "__main__":
    main()
