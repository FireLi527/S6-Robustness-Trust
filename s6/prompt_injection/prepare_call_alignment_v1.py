"""Freeze a two-axis InjecAgent split for call-level task alignment before any rule is written.

Development = dev user cases x dev attacker instructions; test = test users x test attacks.
Cross combinations are dropped so neither the user task nor the attacker instruction (and its
tool) of a test case was seen while designing rules. Labels describe call provenance only.
"""
import ast
import hashlib
import json
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "external/cross_source_v1/injecagent/data"
OUT = ROOT / "data/bipia/call_alignment_v1"
SALT = "call-alignment-v1:"


def order(key: str) -> str:
    return hashlib.sha256((SALT + key).encode("utf-8")).hexdigest()


def halves(keys: list[str], first: int) -> tuple[set, set]:
    ranked = sorted(keys, key=order)
    return set(ranked[:first]), set(ranked[first:])


def source_hashes() -> dict:
    manifest = read_json(ROOT / "external/cross_source_v1/manifest.json")
    hashes = {}
    for name in ("user_cases.jsonl", "test_cases_dh_base.json", "test_cases_ds_base.json"):
        entry = manifest[f"injecagent/data/{name}"]
        digest = entry["sha256"] if isinstance(entry, dict) else entry
        require_hash(SOURCE / name, digest)
        hashes[name] = digest
    return hashes


def build() -> dict:
    users = [json.loads(line) for line in (SOURCE / "user_cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
    cases = {kind: read_json(SOURCE / f"test_cases_{kind}_base.json") for kind in ("dh", "ds")}
    dev_users, test_users = halves([u["User Tool"] for u in users], 8)
    attack_split = {}
    for kind, rows in cases.items():
        instructions = sorted({r["Attacker Instruction"] for r in rows})
        dev, test = halves(instructions, len(instructions) // 2)
        attack_split.update({i: "development" for i in dev} | {i: "test" for i in test})
    out = {"development": {"benign": [], "attack": []}, "test": {"benign": [], "attack": []}}
    for user in users:
        split = "development" if user["User Tool"] in dev_users else "test"
        out[split]["benign"].append({"id": f"benign-{user['User Tool']}", "task": user["User Instruction"],
                                     "tool_name": user["User Tool"],
                                     "parameters": ast.literal_eval(user["Tool Parameters"]), "provenance": "user"})
    for kind, rows in cases.items():
        for index, row in enumerate(rows):
            user_split = "development" if row["User Tool"] in dev_users else "test"
            if user_split != attack_split[row["Attacker Instruction"]]:
                continue
            for step, tool in enumerate(row["Attacker Tools"]):
                out[user_split]["attack"].append({
                    "id": f"{kind}-{index:04d}-{step}", "case": f"{kind}-{index:04d}", "kind": kind, "step": step,
                    "attack_type": row["Attack Type"], "task": row["User Instruction"], "user_tool": row["User Tool"],
                    "tool_name": tool, "parameters": {}, "attacker_instruction": row["Attacker Instruction"],
                    "provenance": "injected"})
    return out


def main() -> None:
    hashes = source_hashes()
    data = build()
    counts = {s: {k: len(v) for k, v in parts.items()} for s, parts in data.items()}
    protocol = {"source": "InjecAgent base (MIT), local frozen copy", "source_sha256": hashes,
                "split": "user cases 8 dev / 9 test and attacker instructions half/half per dh|ds, by salted SHA-256; "
                         "cross combinations dropped", "salt": SALT, "counts": counts,
                "limits": "All 17 user tasks are read-only; attacker tool parameters are not structured in InjecAgent "
                          "(empty); English only.",
                "test_gate": "Rules are designed on development only; test is scored once by the frozen evaluator."}
    with new_run(OUT, protocol):
        for split, parts in data.items():
            write_json(OUT / f"{split}.json", parts)
    print(f"Call-alignment split frozen: {counts}", flush=True)


if __name__ == "__main__":
    main()
