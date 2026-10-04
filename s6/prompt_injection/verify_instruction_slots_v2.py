"""Replay three arms, independently recount metrics and audit model inputs."""
import json
from pathlib import Path
from s6.engineering.artifacts import file_sha256, new_run, read_json, require_hash, write_json
from s6.prompt_injection.instruction_slot_model import DIRECT_PROMPT, DIRECT_SCHEMA, EXTRACT_PROMPT, SLOT_SCHEMA
from s6.prompt_injection.instruction_slot_fewshot import messages, request
from s6.prompt_injection.instruction_slot_evaluation import prediction
from s6.prompt_injection.verify_instruction_slots_v1 import recount

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "results/bipia/instruction_slots_v2"


def expected_messages(row: dict, arm: str, mode: str) -> list[dict]:
    """Reconstruct exact frozen prompts and raw source-only evaluation inputs."""
    if arm == "structured_v2":
        return messages(mode, row[mode])
    if arm == "direct":
        schema, system = DIRECT_SCHEMA, DIRECT_PROMPT
        value = {"user_task": row["task"], "document": row["content"]}
    else:
        schema, system = SLOT_SCHEMA, EXTRACT_PROMPT
        value = {"role": mode, "text": row[mode]}
    return [{"role": "system", "content": system + json.dumps(schema)},
            {"role": "user", "content": json.dumps(value, ensure_ascii=False)}]


def replay(rows: list[dict], run: Path, arms: list[str]) -> dict:
    """No model calls: reproduce decisions and per-kind counts from every raw record."""
    summaries = read_json(run / "summary.json")
    maximum_prompt, maximum_output, incomplete = 0, 0, 0
    quartet_scores = {}
    for arm in arms:
        saved = read_json(run / f"{arm}_predictions.json")
        metric_arm = "direct" if arm == "direct" else "structured"
        for index, row in enumerate(rows):
            records = {}
            for mode in (("direct",) if arm == "direct" else ("task", "content")):
                record = read_json(run / "raw" / f"{index:02d}_{arm}_{mode}.json")
                if record["request"]["messages"] != expected_messages(row, arm, mode):
                    raise ValueError("Prompt mismatch, source alteration, or oracle leakage")
                response = record["response"]
                maximum_prompt = max(maximum_prompt, response["prompt_eval_count"])
                maximum_output = max(maximum_output, response["eval_count"])
                incomplete += int(not response.get("done") or response.get("done_reason") != "stop")
                records[mode] = record
            if prediction(row, records, metric_arm) != saved[index]:
                raise ValueError("Decision replay mismatch")
        recount(rows, saved, summaries[arm], metric_arm)
        for kind in {r["kind"] for r in rows}:
            indices = [i for i, r in enumerate(rows) if r["kind"] == kind]
            recount([rows[i] for i in indices], [saved[i] for i in indices], summaries[arm]["by_kind"][kind], "direct")
        groups = {r["group_id"] for r in rows if r["kind"] == "target"}
        correct = sum(all(saved[i]["decision"] == ("RISK" if r["label"] else "NORMAL")
                          for i, r in enumerate(rows) if r["group_id"] == group and r["kind"] == "target") for group in groups)
        quartet_scores[arm] = {"all_four_correct": correct, "quartets": len(groups)}
    return {"decisions_replayed": len(rows) * len(arms), "max_prompt_tokens": maximum_prompt,
            "max_output_tokens": maximum_output, "incomplete_responses": incomplete, "target_quartets": quartet_scores}


def main() -> None:
    data = ROOT / "data/bipia/instruction_slots_v2"
    design = ROOT / "data/bipia/instruction_slots_v2_design"
    protocol = read_json(RUN / "protocol.json")
    if read_json(RUN / "status.json")["state"] != "COMPLETE":
        raise ValueError("Evaluation incomplete")
    require_hash(design / "protocol.json", protocol["design_sha256"])
    require_hash(ROOT / "s6/prompt_injection/instruction_slot_holdout_v2.py", read_json(data / "protocol.json")["generator_sha256"])
    if read_json(design / "status.json")["finished"] >= read_json(data / "status.json")["started"]:
        raise ValueError("Prompt freeze must precede new data publication")
    protected = {**protocol["protected_sha256"],
                 **{str(p.relative_to(ROOT)): file_sha256(p) for p in RUN.rglob("*.json") if "verification" not in p.parts},
                 str(Path(__file__).relative_to(ROOT)): file_sha256(Path(__file__))}
    for name, digest in protected.items():
        require_hash(ROOT / name, digest)
    rows = read_json(data / "samples.json")
    with new_run(RUN / "verification", {"protected_sha256": protected, "stability": "Repeat first four rows' v2 slots; retain original predictions"}):
        result = replay(rows, RUN, protocol["arms"])
        development = ROOT / "results/bipia/instruction_slots_v2_development"
        result["development_replay"] = replay(read_json(ROOT / "data/bipia/instruction_slots_v1/samples.json"), development, ["structured_v2"])
        stability = []
        for index, row in enumerate(rows[:4]):
            for mode in ("task", "content"):
                repeated = request(mode, row[mode])
                previous = read_json(RUN / "raw" / f"{index:02d}_structured_v2_{mode}.json")
                write_json(RUN / "verification" / f"repeat_{index}_{mode}.json", repeated)
                stability.append({"index": index, "mode": mode,
                                  "same_content": repeated["response"]["message"]["content"] == previous["response"]["message"]["content"]})
        for name, digest in protected.items():
            require_hash(ROOT / name, digest)
        write_json(RUN / "verification/result.json", {**result, "stability": stability})
    print("V2 verification COMPLETE", flush=True)


if __name__ == "__main__":
    main()
