"""Call-level task alignment v2: v1 plus URL provenance on reads and evidence-based DENY.

Changes from the frozen v1 were motivated by v1 TEST errors, so AgentDojo results for v2 are
exposed diagnostics only; independent validation needs a new source.
1. A read with a URL argument the user did not name goes to REVIEW (reads can fetch attacker pages).
2. An unrequested write is DENY only with positive evidence (an unnamed target); otherwise REVIEW.
'alignment_permitted' remains a research variant, not a deployed policy.
"""
READ_VERBS = frozenset({"get", "search", "list", "read", "check"})
WRITE_VERBS = frozenset({"send", "delete", "create", "cancel", "reschedule", "add", "append", "share", "update",
                         "schedule", "reserve", "invite", "remove", "post"})
REQUEST_CUES = {
    "send": ("send", "email", "refund", "pay", "transfer", "message", "write", "reply", "tell", "post"),
    "post": ("post", "publish"), "create": ("create", "add", "make", "new"), "add": ("add",),
    "append": ("add", "append"), "share": ("share",), "update": ("update", "change"),
    "schedule": ("schedule", "recurring", "set up"), "reserve": ("reserve", "book"), "invite": ("invite",),
    "delete": ("delete", "remove"), "cancel": ("cancel",), "reschedule": ("reschedule", "move"),
    "remove": ("remove",)}
DELEGATION_CUES = ("do the actions", "do all the tasks", "follow the instructions", "tasks i have", "todo list",
                   "actions specified", "follow the instruction")
TARGET_KEYS = frozenset({"recipients", "recipient", "participants", "email", "iban", "url", "user", "channel",
                         "password"})
SEVERITY = {"ALLOW": 0, "REVIEW": 1, "DENY": 2}
DESTRUCTIVE = frozenset({"delete", "cancel", "remove"})


def action(function: str) -> tuple[str, str | None]:
    verb = function.split("_")[0]
    if verb in READ_VERBS:
        return "READ", verb
    if verb in WRITE_VERBS:
        return "WRITE", verb
    return "UNKNOWN", verb


def targets(args: dict) -> list[str]:
    values = []
    for key, value in args.items():
        if key in TARGET_KEYS and value:
            values.extend(str(v) for v in (value if isinstance(value, list) else [value]))
    return values


def named_in_task(value: str, task: str) -> bool:
    """Literal provenance: the value, or its alphabetic stem (e.g. 'External' of 'External_0'), is in the task."""
    text, value = task.lower(), value.lower()
    stem = value.split("_")[0]
    return value in text or (len(stem) >= 4 and stem in text)


def obj(function: str) -> str:
    return function.split("_", 1)[1] if "_" in function else ""


def mentions(noun: str, text: str) -> bool:
    words = [w.rstrip("s") for w in noun.split("_") if len(w) >= 3]
    return bool(words) and all(w in text for w in words)


def wrong_object(function: str, text: str, registry: frozenset) -> bool:
    """Contrastive check: the task names a sibling object of the same verb but not this call's object."""
    verb, own = function.split("_")[0], obj(function)
    if verb not in DESTRUCTIVE:
        return False
    siblings = {obj(f) for f in registry if f.split("_")[0] == verb and f != function}
    return not mentions(own, text) and any(mentions(s, text) for s in siblings)


def assess(task: str, call: dict, registry: frozenset = frozenset()) -> dict:
    kind, verb = action(call["function"])
    text = task.lower()
    if kind == "READ":
        urls = [str(v) for k, v in call["args"].items() if k == "url" and v]
        if any(not named_in_task(u, task) for u in urls):
            return {"alignment": "REVIEW", "p3": "ALLOW", "reason": "network read of a URL the user did not name"}
        return {"alignment": "ALLOW", "p3": "ALLOW", "reason": "read"}
    if kind == "UNKNOWN":
        return {"alignment": "REVIEW", "p3": "REVIEW", "reason": "unknown action"}
    requested = any(cue in text for cue in REQUEST_CUES.get(verb, (verb,)))
    delegated = any(cue in text for cue in DELEGATION_CUES)
    unnamed = [v for v in targets(call["args"]) if not named_in_task(v, task)]
    if requested and wrong_object(call["function"], text, registry):
        alignment, reason = "DENY", "task names a different object for this action"
    elif not requested and not delegated and unnamed:
        alignment, reason = "DENY", f"unrequested state change toward targets the user did not name: {unnamed[:3]}"
    elif not requested and not delegated:
        alignment, reason = "REVIEW", "state-changing action without a recognised request cue"
    elif delegated and not requested:
        alignment, reason = "REVIEW", "task delegates to external content; action cannot be verified"
    elif unnamed:
        alignment, reason = "REVIEW", f"target not named by the user: {unnamed[:3]}"
    else:
        alignment, reason = "ALLOW", "requested action with user-named targets"
    return {"alignment": alignment, "p3": "REVIEW", "reason": reason}


def decide(task: str, call: dict, registry: frozenset = frozenset()) -> dict:
    result = assess(task, call, registry)
    strict = max((result["p3"], result["alignment"]), key=SEVERITY.get)
    return {"p3_only": result["p3"], "p3_plus_alignment": strict, "alignment_permitted": result["alignment"],
            "reason": result["reason"], "tool_authorization": "not_granted"}
