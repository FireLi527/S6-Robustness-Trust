"""Greedy offline v2 evaluation with the same precision context in all arms."""
from pathlib import Path
import torch
from s6.engineering.artifacts import write_json
from s6.prompt_injection.relation_sft_v2_io import tokens, messages, score_text, summarize


def evaluate(model, tokenizer, rows: list, examples: list, out: Path) -> dict:
    model.eval()
    model.gradient_checkpointing_disable()
    model.config.use_cache = True
    results = []
    for row in rows:
        for side in ("task", "content"):
            for arm in ("base_zero", "base_fewshot", "adapter_zero"):
                demos = examples if arm == "base_fewshot" else None
                if arm == "adapter_zero":
                    result = generate(model, tokenizer, row, side, demos)
                else:
                    with model.disable_adapter():
                        result = generate(model, tokenizer, row, side, demos)
                record = {"id": row["id"], "side": side, "arm": arm, **result}
                results.append(record)
                write_json(out / "raw" / f"{row['id']}_{side}_{arm}.json", record)
            print(f"Evaluated {row['id']} {side}", flush=True)
    write_json(out / "predictions.json", results)
    return summarize(results, rows)


def generate(model, tokenizer, row: dict, side: str, examples: list | None) -> dict:
    ids = tokens(tokenizer, row, side, examples)
    if len(ids) + 1600 > 4096:
        raise ValueError("Full input/output generation budget exceeded")
    inputs = torch.tensor([ids], device="cuda")
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        output = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=1600,
                                do_sample=False, pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id)
    generated = output[0, len(ids):].tolist()
    text = tokenizer.decode(generated, skip_special_tokens=True)
    finished = bool(generated) and generated[-1] == tokenizer.eos_token_id
    return {"text": text, "finished": finished, "input_ids": ids, "generated_token_ids": generated,
            "input_tokens": len(ids), "output_tokens": len(generated), "input_messages": messages(row, side, examples),
            "score": score_text(text, finished, row["inputs"][side], row["targets"][side])}
