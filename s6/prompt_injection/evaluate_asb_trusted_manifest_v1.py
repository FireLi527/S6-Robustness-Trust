"""Apply the registration-time trusted manifest to both frozen ASB splits; no free parameter to select.

Unlike evaluate_asb_alignment_v1.py, there is no rule family or threshold to pick on development --
manifest()/decide() are parameter-free, so development and test are each evaluated once for
comparable artifacts, not because anything is tuned on development.
"""
import argparse
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, write_json
from s6.prompt_injection.asb_trusted_manifest_v1 import decide, manifest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/asb_alignment_v1"
OUT = ROOT / "results/bipia/asb_trusted_manifest_v1"
CODE = ("asb_trusted_manifest_v1.py", "evaluate_asb_trusted_manifest_v1.py")


def apply(agents: list[dict]) -> dict:
    trusted = manifest(agents)
    benign = attack = benign_hit = attack_hit = full = 0
    per_agent = {}
    rows = 0
    for a in agents:
        scope = trusted[a["agent"]]
        flags = {t["name"]: decide(t["name"], scope) for t in a["tools"]}
        normal_flags = [flags[t["name"]] for t in a["tools"] if t["provenance"] == "normal"]
        attack_flags = [flags[t["name"]] for t in a["tools"] if t["provenance"] == "attack"]
        for _ in a["tasks"]:
            rows += 1
            benign, benign_hit, full = benign + len(normal_flags), benign_hit + sum(normal_flags), full + all(normal_flags)
            attack, attack_hit = attack + len(attack_flags), attack_hit + sum(attack_flags)
            stats = per_agent.setdefault(a["agent"], [0, 0, 0, 0])
            stats[0] += sum(normal_flags); stats[1] += len(normal_flags)
            stats[2] += sum(attack_flags); stats[3] += len(attack_flags)
    return {"benign_allow": benign_hit / benign, "attack_allow": attack_hit / attack,
            "benign_calls": [benign_hit, benign], "attack_calls": [attack_hit, attack],
            "tasks_fully_auto": [full, rows],
            "per_agent": {a: {"benign": s[:2], "attack": s[2:]} for a, s in per_agent.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "test"), required=True)
    split = parser.parse_args().split
    if read_json(DATA / "status.json")["state"] != "COMPLETE":
        raise ValueError("Split not frozen")
    code = {n: file_sha256(Path(__file__).parent / n) for n in CODE}
    agents = read_json(DATA / f"{split}.json")
    with new_run(OUT / split, {"split": split, "code_sha256": code, "data_sha256": file_sha256(DATA / f"{split}.json"),
                               "rule": "registration-time manifest, no free parameter selected on development",
                               "p3_style": "every call REVIEW (no read/write class derivable from these tool names)"}):
        summary = apply(agents)
        write_json(OUT / split / "summary.json", summary)
    print(f"ASB trusted-manifest {split} COMPLETE: benign_allow={summary['benign_allow']} "
          f"attack_allow={summary['attack_allow']}", flush=True)


if __name__ == "__main__":
    main()
