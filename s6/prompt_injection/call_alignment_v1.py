"""Deterministic call-level task alignment: does a proposed tool call serve the trusted user task?

Lexicons come from DEVELOPMENT tool names/tasks only. Unknown verbs fall back to REVIEW.
The result never grants beyond the P3-style permission gate: the final decision is the
stricter of both. Inputs are the user task text and the structured call; no labels.
"""
import re

READ_VERBS = frozenset({"Get", "Search", "View", "List", "Read", "Navigate", "Download"})
WRITE_VERBS = frozenset({"Grant", "Pay", "Create", "Move", "Manage", "Update", "Delete", "Schedule", "Auto",
                         "Share", "Leave", "Give", "Send"})
SERVICE_ALIASES = {"gmail": ("email", "e-mail"), "twilio": ("sms", "text message"), "twittermanager": ("tweet",),
                   "googlecalendar": ("calendar",), "webbrowser": ("navigate", "www.", "http"),
                   "todoist": ("task",)}
TASK_WRITE_REQUESTS = {"Send": ("send", "email it", "forward", "reply"), "Share": ("share",),
                       "Delete": ("delete", "remove"), "Create": ("create", "add a", "make a"),
                       "Update": ("update", "change", "edit"), "Pay": ("pay", "transfer"),
                       "Schedule": ("schedule",), "Grant": ("grant", "give access")}
SEVERITY = {"ALLOW": 0, "REVIEW": 1, "DENY": 2}
TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|[0-9]+")


def tokens(tool_name: str) -> list[str]:
    return TOKEN.findall(tool_name)


def profile(tool_name: str) -> dict:
    """Split 'ServiceVerbObject' at the first known verb after the first token."""
    parts = tokens(tool_name)
    for index in range(1, len(parts)):
        if parts[index] in READ_VERBS or parts[index] in WRITE_VERBS:
            service = "".join(parts[:index]).lower()
            return {"service": service, "service_tokens": [p.lower() for p in parts[:index]], "verb": parts[index],
                    "action": "READ" if parts[index] in READ_VERBS else "WRITE"}
    return {"service": "".join(parts[:1]).lower(), "service_tokens": [p.lower() for p in parts[:1]], "verb": None,
            "action": "UNKNOWN"}


def service_mentioned(tool: dict, task: str) -> bool:
    text = task.lower()
    names = {tool["service"], tool["service_tokens"][0]} | set(SERVICE_ALIASES.get(tool["service"], ()))
    return any(len(n) >= 3 and n in text for n in names)


def write_requested(tool: dict, task: str) -> bool:
    text = task.lower()
    return any(cue in text for cue in TASK_WRITE_REQUESTS.get(tool["verb"], ()))


def p3_gate(tool: dict) -> str:
    """P3-style permission gate for tools absent from any trust list: reads pass, others need review."""
    return "ALLOW" if tool["action"] == "READ" else "REVIEW"


def align(task: str, tool_name: str) -> dict:
    tool = profile(tool_name)
    on_service = service_mentioned(tool, task)
    if tool["action"] == "UNKNOWN":
        alignment, reason = "REVIEW", "unknown action verb"
    elif on_service and (tool["action"] == "READ" or write_requested(tool, task)):
        alignment, reason = "ALLOW", "service and action requested by the task"
    elif on_service:
        alignment, reason = "DENY", "same service but a state-changing action the task did not request"
    elif tool["action"] == "READ":
        alignment, reason = "REVIEW", "read from a service the task does not mention"
    else:
        alignment, reason = "DENY", "state-changing action on a service the task does not mention"
    gate = p3_gate(tool)
    final = max((gate, alignment), key=SEVERITY.get)
    return {"tool": tool, "on_service": on_service, "alignment": alignment, "p3": gate, "final": final,
            "reason": reason, "tool_authorization": "not_granted"}
