"""Export AgentDojo v1.2.2 user/injection tasks with ground-truth calls and freeze a two-axis split.

Run in the isolated WSL venv that has agentdojo installed (no model or API is called):
    ~/.venvs/agentdojo/bin/python -m s6.prompt_injection.prepare_agentdojo_alignment_v1
Per suite, user tasks and injection tasks are each split half/half by salted SHA-256;
development = dev users (+ dev users x dev injections), test likewise. Labels = call provenance.
"""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
from s6.engineering.artifacts import new_run, write_json

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "external/agentdojo"
OUT = ROOT / "data/bipia/agentdojo_alignment_v1"
BENCHMARK = "v1.2.2"
SALT = "agentdojo-alignment-v1:"


def plain(value):
    """Ground-truth arguments may hold dates or models; keep a faithful JSON form."""
    return json.loads(json.dumps(value, default=str))


def calls(task, suite) -> list:
    environment = suite.load_and_inject_default_environment({})
    return [{"function": c.function, "args": plain(dict(c.args))} for c in task.ground_truth(environment)]


def halves(ids: list) -> tuple[set, set]:
    ranked = sorted(ids, key=lambda i: hashlib.sha256((SALT + i).encode()).hexdigest())
    return set(ranked[: len(ranked) // 2]), set(ranked[len(ranked) // 2:])


def export() -> tuple[dict, dict, dict]:
    from agentdojo.task_suite.load_suites import get_suites
    data = {"development": {"benign": [], "attack": []}, "test": {"benign": [], "attack": []}}
    tools, counts = {}, {}
    for name, suite in sorted(get_suites(BENCHMARK).items()):
        tools[name] = [{"name": t.name, "description": t.description,
                        "parameters": plain(t.parameters.model_json_schema())} for t in suite.tools]
        users = {f"{name}/{k}": t for k, t in suite.user_tasks.items()}
        injections = {f"{name}/{k}": t for k, t in suite.injection_tasks.items()}
        dev_users, _ = halves(list(users))
        dev_injections, _ = halves(list(injections))
        injection_calls = {i: calls(t, suite) for i, t in injections.items()}
        for uid, task in users.items():
            split = "development" if uid in dev_users else "test"
            data[split]["benign"].append({"id": uid, "suite": name, "task": task.PROMPT, "calls": calls(task, suite),
                                          "provenance": "user"})
            for iid, goal_calls in injection_calls.items():
                if (iid in dev_injections) == (split == "development"):
                    data[split]["attack"].append({"id": f"{uid}|{iid}", "suite": name, "task": task.PROMPT,
                                                  "injection": iid, "goal": injections[iid].GOAL,
                                                  "calls": goal_calls, "provenance": "injected"})
        counts[name] = {"user_tasks": len(users), "injection_tasks": len(injections), "tools": len(suite.tools)}
    return data, tools, counts


def main() -> None:
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    data, tools, counts = export()
    sizes = {s: {k: len(v) for k, v in parts.items()} for s, parts in data.items()}
    protocol = {"source": "AgentDojo (MIT)", "repo_commit": commit, "package_version": version("agentdojo"),
                "benchmark_version": BENCHMARK, "suites": counts, "sizes": sizes, "salt": SALT,
                "split": "per suite, user tasks and injection tasks halved by salted SHA-256; cross pairs dropped",
                "calls": "ground_truth() on the default environment; injection calls are the attacker goal calls",
                "test_gate": "Rules designed on development only; test scored once by a frozen evaluator"}
    with new_run(OUT, protocol):
        write_json(OUT / "tools.json", tools)
        for split, parts in data.items():
            write_json(OUT / f"{split}.json", parts)
    print(f"AgentDojo alignment data frozen: {sizes}", flush=True)


if __name__ == "__main__":
    main()
