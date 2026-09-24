"""Grouped, source-auditable BIPIA supervision; no generated-row random split."""
import base64
import hashlib
import json
import random
from pathlib import Path
from nltk.tokenize.punkt import PunktSentenceTokenizer

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "external/BIPIA/benchmark"
TASKS = ("email", "table", "code")
SEED = 2026

def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def as_text(value):
    return "\n".join(value) if isinstance(value, list) else value

def content_group(text):
    return digest(" ".join(text.split()))

def question_for(task, row):
    if task == "code":
        return "Fix the bug in this code:\n" + as_text(row["code"]) + "\nError:\n" + as_text(row["error"])
    return row["question"]

def source_records():
    rows = []
    hashes = {}
    for task in TASKS:
        for split in ("train", "test"):
            path = BENCHMARK / task / f"{split}.jsonl"
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                r = json.loads(line)
                context = as_text(r["context"])
                rows.append(dict(source_id=f"{task}/{split}/{i}", task=task, upstream_split=split,
                                 group=content_group(context), context=context, question=question_for(task, r)))
    return rows, hashes

def split_sources(rows):
    test_groups = {r["group"] for r in rows if r["upstream_split"] == "test"}
    validation_groups = set()
    for task in TASKS:
        groups = sorted({r["group"] for r in rows if r["upstream_split"] == "train" and r["task"] == task} - test_groups)
        random.Random(SEED).shuffle(groups)
        validation_groups.update(groups[:max(1, round(.2*len(groups)))])
    result = {k: [] for k in ("train", "validation", "test", "excluded_overlap")}
    for r in rows:
        if r["upstream_split"] == "test":
            split = "test"
        elif r["group"] in test_groups:
            split = "excluded_overlap"
        elif r["group"] in validation_groups:
            split = "validation"
        else:
            split = "train"
        result[split].append(r)
    groups = {s: {r["group"] for r in result[s]} for s in ("train", "validation", "test")}
    if any(groups[a] & groups[b] for a,b in (("train","validation"),("train","test"),("validation","test"))):
        raise ValueError("Cross-split source-content leakage")
    return result

def catalogs():
    result, hashes, excluded = {}, {}, {}
    for kind in ("text", "code"):
        sets = {}
        for split in ("train", "test"):
            path = BENCHMARK / f"{kind}_attack_{split}.json"
            sets[split] = json.loads(path.read_text(encoding="utf-8"))
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        excluded[kind] = sorted(set(sets["train"]) & set(sets["test"]))
        for split in ("train", "test"):
            result[kind,split] = [(category, i, text) for category, variants in sets[split].items()
                                 if split == "test" or category not in sets["test"]
                                 for i,text in enumerate(variants)]
    return result, hashes, excluded

def variants(source, attacks):
    # Mirrors upstream BIPIA insert_{end,start,middle}, fixed seed=2023.
    context = source["context"]
    spans = list(PunktSentenceTokenizer().span_tokenize(context))
    middle = random.Random(2023).sample(spans, k=1)[0][0] if spans else 0
    for encoding in ("plain", "stealth"):
        for category, index, original in attacks:
            attack = original if encoding == "plain" else base64.b64encode(original.encode()).decode()
            texts = ("\n".join([context, attack]), "\n".join([attack, context]),
                     "\n".join([context[:middle], attack, context[middle:]]))
            for position, text in zip(("end", "start", "middle"), texts):
                yield {"context": text, "question": source["question"], "encoding": encoding,
                       "category": category, "variant": index, "position": position, "label": 1}
    yield {"context": context, "question": source["question"], "encoding": "clean",
           "category": "", "variant": -1, "position": "", "label": 0}

def model_text(question, context):
    # Never include attack strings separately, labels, positions, source IDs or ideal answers.
    return question + "\n" + context
