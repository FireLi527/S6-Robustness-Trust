"""Static external check of the frozen Code comment signal; never executes samples."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import random
import textwrap
import tokenize
from pathlib import Path

from code_context_signal import assess_comment_redirection
from detector import detect_prompt_injection
from supervised_data import ROOT


DATA = ROOT / "data/bipia/code_external_v1"
RESULTS = ROOT / "results/bipia/code_external_v1"
BENCHMARK = ROOT / "external/RepoGuardBench"
SIGNAL = Path(__file__).with_name("code_context_signal.py")
QUESTION = "Fix the bug in this code and explain the change."
SEED = 2026
GOALS = ("CANARY_READ", "CANARY_EXFIL", "TEST_DELETE", "UNAUTH_SHELL", "BACKDOOR")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def benchmark_payloads() -> dict[str, str]:
    """Read literal upstream templates via AST, without importing upstream code."""
    source = (BENCHMARK / "repoguard/attacks/carriers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    result = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_payload_"):
            continue
        return_node = next((part for part in node.body if isinstance(part, ast.Return)), None)
        if return_node is None or not isinstance(return_node.value, ast.Call):
            raise ValueError(f"Unexpected upstream payload function: {node.name}")
        dedent_call = return_node.value.func.value
        if not isinstance(dedent_call, ast.Call) or not isinstance(dedent_call.func, ast.Attribute) or dedent_call.func.attr != "dedent":
            raise ValueError(f"Unexpected upstream payload structure: {node.name}")
        result[node.name.removeprefix("_payload_").upper()] = textwrap.dedent(ast.literal_eval(dedent_call.args[0])).strip()
    if set(result) != set(GOALS):
        raise ValueError(f"Unexpected upstream goals: {sorted(result)}")
    return result


def source_sample(path: Path) -> tuple[str, str] | None:
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8")
        tree = ast.parse(content)
    except (OSError, UnicodeError, SyntaxError, ValueError):
        return None
    lines = content.splitlines()
    nodes = list(tree.body)
    for parent in tree.body:
        if isinstance(parent, ast.ClassDef):
            nodes.extend(parent.body)
    for node in nodes:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not hasattr(node, "end_lineno"):
            continue
        snippet = "\n".join(lines[node.lineno - 1:node.end_lineno])
        if not 500 <= len(snippet) <= 6000:
            continue
        comments = [tok for tok in tokenize.generate_tokens(io.StringIO(snippet).readline)
                    if tok.type == tokenize.COMMENT]
        docstring = bool(ast.get_docstring(node))
        if comments or docstring:
            return snippet, sha(raw)
    return None


def prepare() -> None:
    if (DATA / "protocol.json").exists() or (DATA / "samples.jsonl").exists():
        raise FileExistsError("External evaluation dataset already frozen")
    if not BENCHMARK.is_dir():
        raise FileNotFoundError(BENCHMARK)
    import pandas
    import scipy

    rows = []
    for name, package in (("pandas", pandas), ("scipy", scipy)):
        root = Path(package.__file__).parent
        candidates = []
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(root)
            if any(part.startswith("test") or part in {"tests", "_testing"} for part in relative.parts):
                continue
            sample = source_sample(path)
            if sample:
                snippet, file_hash = sample
                candidates.append((relative.as_posix(), snippet, file_hash))
        random.Random(SEED).shuffle(candidates)
        if len(candidates) < 50:
            raise ValueError(f"Only {len(candidates)} usable {name} files")
        for relative, snippet, file_hash in candidates[:50]:
            rows.append({"kind": "natural_clean", "source_id": f"{name}/{relative}",
                         "source_file_sha256": file_hash, "question": QUESTION,
                         "content": snippet})

    payloads = benchmark_payloads()
    for tier, filename in (("core", "repoguardbench_core.jsonl"), ("applied", "repoguardbench_real.jsonl")):
        for line in (BENCHMARK / "data" / filename).read_text(encoding="utf-8").splitlines():
            task = json.loads(line)
            target = task["target_py"]
            source = task["files"][target]
            common = {"tier": tier, "source_id": task["task_id"], "question": task["issue_text"],
                      "target_file": target}
            rows.append({"kind": "benchmark_clean", **common, "goal": "", "content": source})
            for goal in GOALS:
                payload = payloads[goal]
                block = "\n".join("# " + line for line in payload.splitlines())
                rows.append({"kind": "benchmark_attack", **common, "goal": goal,
                             "content": block + "\n\n" + source})
    if len(rows) != 100 + 94 * 6:
        raise ValueError(f"Unexpected dataset size {len(rows)}")
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    commit = (BENCHMARK / ".git/refs/heads/main").read_text(encoding="ascii").strip()
    protocol = {"status": "FROZEN_BEFORE_SCORING", "seed": SEED,
                "benchmark_url": "https://github.com/DaoyuanLi2816/RepoGuardBench",
                "benchmark_commit": commit, "benchmark_license": "CC BY 4.0; see LICENSE-DATA",
                "benchmark_carrier": "code_comment", "benchmark_goals": GOALS,
                "benchmark_core_tasks": 80, "benchmark_applied_tasks": 14,
                "natural_source": {"pandas": pandas.__version__, "scipy": scipy.__version__},
                "natural_files_per_package": 50, "question": QUESTION,
                "sample_sha256": sha(raw), "signal_sha256": sha(SIGNAL.read_bytes()),
                "limitations": ["Benchmark attacks are published, synthetic, inert templates, not attacks scraped from real repositories.",
                                "Applied tasks are hand-curated synthetic micro-repositories, not real GitHub repositories.",
                                "Natural clean samples are unmodified open-source code, not independently human-labelled benign examples.",
                                "Five attacks per benchmark task share its clean source; counts are correlated.",
                                "This is static detection, not LLM-agent attack success."]}
    DATA.mkdir(parents=True, exist_ok=False)
    (DATA / "samples.jsonl").write_bytes(raw)
    (DATA / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FROZEN {len(rows)} rows; sha256={sha(raw)}")


def counts(rows: list[dict], key: str) -> dict:
    return {"flagged": sum(row[key] for row in rows), "total": len(rows),
            "rate": sum(row[key] for row in rows) / len(rows)}


def evaluate() -> None:
    if (RESULTS / "summary.json").exists():
        raise FileExistsError("External evaluation already exists; do not overwrite")
    protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
    raw = (DATA / "samples.jsonl").read_bytes()
    if protocol["status"] != "FROZEN_BEFORE_SCORING" or sha(raw) != protocol["sample_sha256"]:
        raise ValueError("Frozen samples changed")
    if sha(SIGNAL.read_bytes()) != protocol["signal_sha256"]:
        raise ValueError("Comment signal changed since dataset freeze")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    predictions = []
    for row in rows:
        rule = detect_prompt_injection(row["content"]).decision != "ALLOW"
        comment = assess_comment_redirection(row["content"])["decision"] != "ALLOW"
        predictions.append({"kind": row["kind"], "tier": row.get("tier", ""),
                            "source_id": row["source_id"], "goal": row.get("goal", ""),
                            "rule": rule, "comment": comment, "rule_or_comment": rule or comment})
    summary = {"status": "COMPLETE", "sample_sha256": protocol["sample_sha256"],
               "signal_sha256": protocol["signal_sha256"], "benchmark_commit": protocol["benchmark_commit"],
               "metrics": {kind: {name: counts([r for r in predictions if r["kind"] == kind], name)
                                  for name in ("rule", "comment", "rule_or_comment")}
                           for kind in ("natural_clean", "benchmark_clean", "benchmark_attack")},
               "attack_by_goal": {goal: {name: counts([r for r in predictions if r["goal"] == goal], name)
                                         for name in ("rule", "comment", "rule_or_comment")}
                                  for goal in GOALS},
               "attack_by_tier": {tier: {name: counts([r for r in predictions if r["kind"] == "benchmark_attack" and r["tier"] == tier], name)
                                        for name in ("rule", "comment", "rule_or_comment")}
                                  for tier in ("core", "applied")},
               "limitations": protocol["limitations"]}
    RESULTS.mkdir(parents=True, exist_ok=False)
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (RESULTS / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "evaluate"))
    args = parser.parse_args()
    prepare() if args.mode == "prepare" else evaluate()
