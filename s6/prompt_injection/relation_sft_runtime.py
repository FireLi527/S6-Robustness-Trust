"""NF4 LoRA runtime isolated from existing baselines; no model uploads."""
import random
import time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from s6.engineering.artifacts import write_json
from s6.prompt_injection.relation_sft_io import prompt_ids, score, messages


def load_model(path: Path):
    """Only adapter parameters train; keep tied embeddings BF16 to bound memory."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required; no silent CPU fallback")
    torch.manual_seed(2026)
    config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(str(path), local_files_only=True, trust_remote_code=False,
                quantization_config=config, device_map={"": 0}, dtype=torch.bfloat16, attn_implementation="sdpa")
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False})
    model.get_input_embeddings().to(torch.bfloat16)
    model.get_output_embeddings().to(torch.bfloat16)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, target_modules=["q_proj", "v_proj"], bias="none", task_type="CAUSAL_LM"))
    if any(p.requires_grad and "lora_" not in name for name, p in model.named_parameters()):
        raise ValueError("Unexpected non-adapter trainable parameter")
    return model


def train(model, records: list[dict], out: Path) -> list[dict]:
    """Three fixed epochs, accumulate four single examples; no eval-driven selection."""
    model.train()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=2e-4, weight_decay=0.01)
    trace = []
    for epoch in range(3):
        order = list(range(len(records)))
        random.Random(2026 + epoch).shuffle(order)
        for start in range(0, len(order), 4):
            block = order[start:start + 4]
            optimizer.zero_grad(set_to_none=True)
            loss_sum = 0.0
            for index in block:
                record = records[index]
                ids = torch.tensor([record["input_ids"]], device="cuda")
                labels = torch.tensor([record["labels"]], device="cuda")
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    loss = model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels).loss
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite training loss")
                (loss / len(block)).backward()
                loss_sum += loss.detach().float().item()
            norm = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            if not torch.isfinite(norm):
                raise ValueError("Non-finite gradient norm")
            optimizer.step()
            trace.append({"step": len(trace) + 1, "epoch": epoch + 1, "loss": loss_sum / len(block),
                          "peak_gpu_bytes": torch.cuda.max_memory_allocated()})
            write_json(out / "training_trace.json", trace)
            print(f"Train epoch {epoch + 1}/3 step {len(trace)} loss {trace[-1]['loss']:.4f}", flush=True)
    model.save_pretrained(out / "adapter", safe_serialization=True)
    return trace


def generate(model, tokenizer, row: dict, side: str, examples: list[dict] | None = None) -> dict:
    ids = prompt_ids(tokenizer, row, side, examples)
    if len(ids) + 1200 > 4096:
        raise ValueError("Inference complete-input budget exceeded; no truncation")
    inputs = torch.tensor([ids], device="cuda")
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=1200,
                                do_sample=False, pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id)
    generated = output[0, len(ids):].tolist()
    text = tokenizer.decode(generated, skip_special_tokens=True)
    finished = bool(generated) and generated[-1] == tokenizer.eos_token_id
    return {"text": text, "finished": finished, "input_tokens": len(ids), "output_tokens": len(generated),
            "input_messages": messages(row, side, examples), "input_ids": ids, "generated_token_ids": generated,
            "seconds": time.perf_counter() - started, "score": score(text, finished, row["inputs"][side], row["targets"][side])}
