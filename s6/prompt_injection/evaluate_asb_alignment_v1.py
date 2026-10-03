"""Choose a rule on ASB development by the pre-declared criterion, then apply it once to test.

P3 here cannot classify these tools as reads, so P3-style gating sends every call to review;
the research variant auto-allows only tools the frozen rule marks as task-aligned.
"""
import argparse
from pathlib import Path
import sys
from s6.engineering.artifacts import file_sha256, new_run, read_json, write_json
from s6.prompt_injection.asb_alignment_v1 import allowed, candidates, cosine, select, tool_text

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/bipia/asb_alignment_v1"
OUT = ROOT / "results/bipia/asb_alignment_v1"
MODEL_CACHE = ROOT / "external/minilm_cache"
CODE = ("asb_alignment_v1.py", "evaluate_asb_alignment_v1.py")


def embeddings(agents: list, cache: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import semantic_detector
    texts = sorted({t for a in agents for t in a["tasks"]} | {tool_text(t) for a in agents for t in a["tools"]})
    vectors = semantic_detector.extract_embeddings(texts, cache, MODEL_CACHE)
    return {t: vectors[semantic_detector.text_sha256(t)] for t in texts}


def similarity(agents: list, vec: dict) -> list:
    return [{"agent": a["agent"], "task": task, "tools": a["tools"],
             "scores": [cosine(vec[task], vec[tool_text(t)]) for t in a["tools"]]} for a in agents for task in a["tasks"]]


def apply(rows: list, rule: tuple) -> dict:
    benign = attack = benign_hit = attack_hit = full = 0
    per_agent = {}
    for row in rows:
        flags = allowed(row["scores"], rule)
        normal = [f for f, t in zip(flags, row["tools"]) if t["provenance"] == "normal"]
        hostile = [f for f, t in zip(flags, row["tools"]) if t["provenance"] == "attack"]
        benign, benign_hit, full = benign + len(normal), benign_hit + sum(normal), full + all(normal)
        attack, attack_hit = attack + len(hostile), attack_hit + sum(hostile)
        stats = per_agent.setdefault(row["agent"], [0, 0, 0, 0])
        stats[0] += sum(normal); stats[1] += len(normal); stats[2] += sum(hostile); stats[3] += len(hostile)
    return {"benign_allow": benign_hit / benign, "attack_allow": attack_hit / attack, "benign_calls": [benign_hit, benign],
            "attack_calls": [attack_hit, attack], "tasks_fully_auto": [full, len(rows)],
            "per_agent": {a: {"benign": s[:2], "attack": s[2:]} for a, s in per_agent.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "test"), required=True)
    split = parser.parse_args().split
    if read_json(DATA / "status.json")["state"] != "COMPLETE":
        raise ValueError("Split not frozen")
    code = {n: file_sha256(Path(__file__).parent / n) for n in CODE}
    if split == "test":
        if read_json(OUT / "development/protocol.json")["code_sha256"] != code:
            raise ValueError("Code changed after development selection")
        rule = tuple(read_json(OUT / "development/summary.json")["selected_rule"])
    agents = read_json(DATA / f"{split}.json")
    with new_run(OUT / split, {"split": split, "code_sha256": code, "data_sha256": file_sha256(DATA / f"{split}.json"),
                               "p3_style": "every call REVIEW (no read/write class derivable from these tool names)"}):
        rows = similarity(agents, embeddings(agents, OUT / split / "embedding_cache.npz"))
        if split == "development":
            grid = {r: apply(rows, r) for r in candidates()}
            rule = select(grid)
            summary = {"selected_rule": list(rule), "selected": grid[rule],
                       "grid": {f"{r[0]}={r[1]}": {k: grid[r][k] for k in ("benign_allow", "attack_allow")} for r in grid}}
        else:
            summary = {"selected_rule": list(rule), "result": apply(rows, rule)}
        write_json(OUT / split / "summary.json", summary)
    print(f"ASB alignment {split} COMPLETE: rule {rule}", flush=True)


if __name__ == "__main__":
    main()
