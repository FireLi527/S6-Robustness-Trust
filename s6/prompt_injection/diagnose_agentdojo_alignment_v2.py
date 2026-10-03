"""Exposed-data diagnostic for alignment v2 on both AgentDojo splits; never an independent test claim."""
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, write_json
from s6.prompt_injection.agentdojo_alignment_v2 import action, decide
from s6.prompt_injection.evaluate_agentdojo_alignment_v1 import SYSTEMS, metrics

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/agentdojo_alignment_v1"
OUT = ROOT / "results/bipia/agentdojo_alignment_v2_diagnostic"


def score(rows: list, registry: dict) -> list:
    return [{"id": r["id"], "suite": r["suite"], "provenance": r["provenance"],
             "calls": [{"function": c["function"], "write": action(c["function"])[0] != "READ",
                        **decide(r["task"], c, registry[r["suite"]])} for c in r["calls"]]} for r in rows]


def main() -> None:
    registry = {s: frozenset(t["name"] for t in tools) for s, tools in read_json(DATA / "tools.json").items()}
    code = {n: file_sha256(Path(__file__).parent / n) for n in
            ("agentdojo_alignment_v2.py", "diagnose_agentdojo_alignment_v2.py", "evaluate_agentdojo_alignment_v1.py")}
    with new_run(OUT, {"code_sha256": code, "status": "exposed diagnostic: v2 changes were motivated by v1 test errors",
                       "data_sha256": {s: file_sha256(DATA / f"{s}.json") for s in ("development", "test")}}):
        summary = {}
        for split in ("development", "test"):
            parts = read_json(DATA / f"{split}.json")
            items = score(parts["benign"] + parts["attack"], registry)
            write_json(OUT / f"{split}_decisions.json", items)
            summary[split] = {s: metrics(items, s) for s in SYSTEMS}
        write_json(OUT / "summary.json", summary)
    print("AgentDojo alignment v2 diagnostic COMPLETE", flush=True)


if __name__ == "__main__":
    main()
