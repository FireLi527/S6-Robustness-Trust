"""Freeze an agent-level ASB split for semantic task-tool alignment before any rule is chosen.

Agents (each with its own tasks, 2 normal tools and 40 attacker tools) are split 5/5 by salted
SHA-256, so test tasks and tools are entirely unseen during development. Labels = tool provenance.
"""
import hashlib
import json
from pathlib import Path
import subprocess
from s6.engineering.artifacts import file_sha256, new_run, write_json

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "external/asb"
OUT = ROOT / "data/bipia/asb_alignment_v1"
SALT = "asb-alignment-v1:"
FILES = ("agent_task.jsonl", "all_normal_tools.jsonl", "all_attack_tools.jsonl")


def lines(name: str) -> list:
    return [json.loads(x) for x in (SOURCE / "data" / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def build() -> dict:
    agents = {a["agent_name"]: a["tasks"] for a in lines("agent_task.jsonl")}
    ranked = sorted(agents, key=lambda a: hashlib.sha256((SALT + a).encode()).hexdigest())
    split_of = {a: ("development" if i < len(ranked) // 2 else "test") for i, a in enumerate(ranked)}
    tools = {a: [] for a in agents}
    for t in lines("all_normal_tools.jsonl"):
        tools[t["Corresponding Agent"]].append({"name": t["Tool Name"], "description": t["Description"],
                                                "provenance": "normal"})
    for t in lines("all_attack_tools.jsonl"):
        tools[t["Corresponding Agent"]].append({"name": t["Attacker Tool"], "description": t["Description"],
                                                "provenance": "attack", "aggressive": t["Aggressive"] == "True"})
    out = {"development": [], "test": []}
    for agent, tasks in agents.items():
        out[split_of[agent]].append({"agent": agent, "tasks": tasks, "tools": tools[agent]})
    return out


def main() -> None:
    commit = subprocess.run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    data = build()
    sizes = {s: {"agents": len(v), "tasks": sum(len(a["tasks"]) for a in v),
                 "normal_tools": sum(t["provenance"] == "normal" for a in v for t in a["tools"]),
                 "attack_tools": sum(t["provenance"] == "attack" for a in v for t in a["tools"])} for s, v in data.items()}
    protocol = {"source": "Agent Security Bench (MIT)", "repo_commit": commit,
                "source_sha256": {n: file_sha256(SOURCE / "data" / n) for n in FILES}, "salt": SALT, "sizes": sizes,
                "split": "agents 5/5 by salted SHA-256; test tasks and tools unseen during development",
                "unit": "benign = (task, each normal tool of its agent); attack = (task, each attacker tool of its agent)",
                "test_gate": "Rule family and parameter chosen on development by a pre-declared criterion; test once"}
    with new_run(OUT, protocol):
        for split, agents in data.items():
            write_json(OUT / f"{split}.json", agents)
    print(f"ASB alignment split frozen: {sizes}", flush=True)


if __name__ == "__main__":
    main()
