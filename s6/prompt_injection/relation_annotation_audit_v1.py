"""Read-only representation audit; diagnostics never replace frozen strict scores."""
from collections import Counter, defaultdict
import json

PAYLOAD_ROLES = ("object", "data")
TRANSFER_OPS = frozenset({"发送", "发", "贴", "合并", "写入", "导出", "复制", "传入", "给出", "回复",
                          "报告", "显示", "展示", "写出", "发布", "抄送", "发出"})
NEGATION_MARKERS = ("不", "禁止", "无需", "保留", "不动")
ORDER_MARKERS = frozenset({"先", "再", "然后", "随后", "之后再", "最后再", "立即", "现在", "否则", "同时"})
SCOPE_MARKERS = ("整个", "所有", "全部", "前缀", "两列", "命名空间", "仅", "只")


def _strings(value: dict) -> list[str]:
    """Every content string except evidence, which often repeats the whole input."""
    found = list(value["constraints"]) + list(value["missing_context"])
    for action in value["actions"]:
        found.append(action["operation"])
        found.extend(action["conditions"])
        found.extend(b["text"] for b in action["bindings"] if b["text"] is not None)
    return found


def covered(atom: str, strings: list[str]) -> bool:
    """Literal containment either way; a diagnostic of retained wording, not meaning."""
    return any(atom in s or (len(s) >= 2 and s in atom) for s in strings)


def reference_inventory(sides: list[dict]) -> dict:
    """Count how frozen references encode recurring representation choices."""
    payload, null_object, statuses, negations, conditions = (defaultdict(Counter), Counter(), Counter(),
                                                             Counter(), Counter())
    scoped_spans, text_roles, constraint_list = [], defaultdict(set), []
    for side in sides:
        target, has_missing = side["target"], bool(side["target"]["missing_context"])
        for action in target["actions"]:
            roles = {b["role"] for b in action["bindings"]}
            if action["operation"] in TRANSFER_OPS:
                payload[action["operation"]][",".join(sorted(roles & set(PAYLOAD_ROLES))) or "none"] += 1
            nulls = [b for b in action["bindings"] if b["text"] is None]
            null_object["null_placeholder" if nulls else
                        "no_payload_binding" if not roles & set(PAYLOAD_ROLES) else "payload_present"] += 1
            for b in action["bindings"]:
                statuses[(b["status"], "with_missing" if has_missing else "without_missing")] += 1
                if b["text"] is not None:
                    text_roles[b["text"]].add(b["role"])
                    if any(m in b["text"] for m in SCOPE_MARKERS):
                        scoped_spans.append({"id": side["id"], "side": side["side"], "role": b["role"], "text": b["text"]})
            if action["kind"] == "prohibited":
                negations["prohibited_action"] += 1
            for c in action["conditions"]:
                conditions["marker_only" if c in ORDER_MARKERS else "content_bearing"] += 1
        for text in target["constraints"]:
            negations["negative_constraint" if any(m in text for m in NEGATION_MARKERS) else "other_constraint"] += 1
            constraint_list.append({"id": side["id"], "side": side["side"], "text": text})
    mixed = {t: sorted(r) for t, r in text_roles.items() if len(r) > 1}
    return {"reference_sides": len(sides),
            "transfer_payload_roles": {op: dict(c) for op, c in sorted(payload.items())},
            "action_payload_binding": dict(null_object),
            "binding_status": {f"{s}|{m}": n for (s, m), n in sorted(statuses.items())},
            "negative_restriction_encoding": dict(negations), "condition_granularity": dict(conditions),
            "scope_words_inside_spans": scoped_spans, "same_text_multiple_roles": mixed,
            "constraints": constraint_list, "unknown_status_rows": unknown_rows(sides)}


def unknown_rows(sides: list[dict]) -> list[dict]:
    """Rows with a missing-information note, showing whether any binding is unmapped."""
    rows = []
    for side in sides:
        target = side["target"]
        if target["missing_context"]:
            bindings = [b for a in target["actions"] for b in a["bindings"] if b["text"] is not None]
            rows.append({"id": side["id"], "side": side["side"], "missing": target["missing_context"],
                         "unmapped": [b["text"] for b in bindings if b["status"] == "unmapped"],
                         "explicit": [b["text"] for b in bindings if b["status"] == "explicit"]})
    return rows


def _best_candidate(gold: dict, predicted: list[dict]) -> dict | None:
    """Prefer the identical operation; otherwise accept a containing/contained operation span."""
    op = gold["operation"]
    same = [a for a in predicted if a["operation"] == op] or \
        [a for a in predicted if op in a["operation"] or a["operation"] in op]
    if not same:
        return None
    texts = {b["text"] for b in gold["bindings"]}
    return max(same, key=lambda a: (len(texts & {b["text"] for b in a["bindings"]}), a["kind"] == gold["kind"]))


def _binding_diffs(gold: dict, candidate: dict, strings: list[str]) -> list[str]:
    diffs = []
    pred = {(b["role"], b["status"], b["text"]) for b in candidate["bindings"]}
    for b in gold["bindings"]:
        if (b["role"], b["status"], b["text"]) in pred:
            continue
        if b["text"] is None:
            diffs.append("null_placeholder")
        elif any(t == b["text"] for _, _, t in pred):
            same = [(r, s) for r, s, t in pred if t == b["text"]]
            diffs.append("role" if all(r != b["role"] for r, _ in same) else "status")
        elif covered(b["text"], [t for _, _, t in pred if t]):
            diffs.append("span_boundary")
        elif covered(b["text"], strings):
            diffs.append("binding_elsewhere")
        else:
            diffs.append("binding_missing")
    gold_texts = {(b["role"], b["text"]) for b in gold["bindings"]}
    for role, _, text in pred:
        if text is None and (role, None) not in gold_texts:
            diffs.append("null_placeholder")
        elif text is not None and not covered(text, [t for _, t in gold_texts if t]):
            diffs.append("binding_extra")
    return diffs


def _condition_diffs(gold: dict, candidate: dict, strings: list[str]) -> list[str]:
    diffs = []
    for c in gold["conditions"]:
        if c in candidate["conditions"]:
            continue
        diffs.append("condition_span" if covered(c, candidate["conditions"]) else
                     "condition_moved" if covered(c, strings) else "condition_missing")
    if any(not covered(c, gold["conditions"]) for c in candidate["conditions"]):
        diffs.append("condition_extra")
    return diffs


MISSING_DIFFS = frozenset({"binding_missing", "condition_missing"})


def attribute_side(prediction: dict | None, target: dict) -> dict:
    """Explain each reference unit by literal diffs; not a semantic-equivalence judge."""
    if prediction is None:
        return {"valid": False, "actions": [], "lists": [], "extra_actions": []}
    strings, predicted = _strings(prediction), prediction["actions"]
    actions, used = [], set()
    for index, gold in enumerate(target["actions"]):
        candidate = _best_candidate(gold, predicted)
        if candidate is None:
            info = covered(gold["operation"], strings)
            atoms = [b["text"] for b in gold["bindings"] if b["text"]] + gold["conditions"]
            category = ("restructured" if info and all(covered(a, strings) for a in atoms) else "information_missing")
            actions.append({"index": index, "operation": gold["operation"], "category": category,
                            "diffs": ["operation_not_separate" if info else "action_missing"]})
            continue
        used.add(id(candidate))
        order = [] if predicted.index(candidate) == index else ["action_order"]
        order += [] if candidate["operation"] == gold["operation"] else ["operation_span"]
        diffs = order +([] if candidate["kind"] == gold["kind"] else ["kind"]) \
            + _binding_diffs(gold, candidate, strings) + _condition_diffs(gold, candidate, strings)
        category = ("exact" if not diffs else "information_missing" if MISSING_DIFFS & set(diffs)
                    else "representation_only")
        actions.append({"index": index, "operation": gold["operation"], "category": category, "diffs": sorted(diffs)})
    lists = []
    for field in ("constraints", "missing_context"):
        for text in target[field]:
            category = ("exact" if text in prediction[field] else
                        "representation_only" if covered(text, strings) else "information_missing")
            lists.append({"field": field, "text": text, "category": category})
    gold_strings = _strings(target)
    extra = [{"operation": a["operation"], "kind": a["kind"],
              "grounded_in_reference": covered(a["operation"], gold_strings)}
             for a in predicted if id(a) not in used]
    return {"valid": True, "actions": actions, "lists": lists, "extra_actions": extra}


def parse(prediction: dict) -> dict | None:
    """Only frozen-valid outputs are attributed; invalid ones stay invalid."""
    if not prediction["score"]["valid"]:
        return None
    return json.loads(prediction["text"])


def summarize_attribution(items: list[dict]) -> dict:
    """Aggregate reference units by category; denominators are reported explicitly."""
    units, diffs, extras = Counter(), Counter(), Counter()
    for item in items:
        result = item["attribution"]
        if not result["valid"]:
            units["contract_invalid"] += item["reference_units"]
            continue
        for unit in result["actions"] + result["lists"]:
            units[unit["category"]] += 1
            diffs.update(unit.get("diffs", []))
        for extra in result["extra_actions"]:
            extras["grounded" if extra["grounded_in_reference"] else "not_in_reference"] += 1
    return {"inputs": len(items), "invalid_inputs": sum(not i["attribution"]["valid"] for i in items),
            "reference_units": sum(i["reference_units"] for i in items), "unit_categories": dict(units),
            "diff_counts": dict(sorted(diffs.items())), "extra_predicted_actions": dict(extras)}
