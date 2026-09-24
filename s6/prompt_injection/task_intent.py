"""Resolve task intent from trusted user input or server-issued demo context.

Untrusted content is used only to bind a context, never to infer the user's goal.
Demo presets are new workflow assumptions, not recovered P3 benchmark ground truth.
"""
from collections import OrderedDict
import hashlib
import re
import secrets
import threading

CONTEXTS = OrderedDict()
LOCK = threading.Lock()
MAX_CONTEXTS = 2048
PRESETS = {
    "read_email": "Read the email and summarize the information relevant to the user.",
    "search_documents": "Review the retrieved documents and identify information relevant to the user's document search.",
    "create_calendar_event": "Review the meeting notes and summarize the proposed schedule and follow-up items for the user.",
    "send_email": "Review the email thread and summarize the requested communication and follow-up items for the user.",
    "delete_records": "Review the records-management request and explain the proposed changes for the user.",
    "access_secret": "Review the access request and summarize its stated purpose and scope for the user.",
}

def category(question):
    # Descriptive labels only; P2 always receives the complete original task.
    for name, pattern in (
        ("summarize", r"summari[sz]e|summary|总结|摘要|概括"),
        ("translate", r"translat|翻译"),
        ("retrieve", r"search|find|查找|搜索|检索"),
        ("review", r"review|explain|审查|检查|解释"),
        ("question_answering", r"\?|？|^(who|what|when|where|why|how)\b"),
    ):
        if re.search(pattern, question, re.I):
            return name
    return "user_request"

def description(question, source):
    return {"status": "RESOLVED" if question else "NEEDS_TASK", "question": question,
            "source": source, "category": category(question) if question else "unknown",
            "method": "trusted-context-resolution-v1", "affects_tool_policy": False,
            "demo_assumption": source == "demo_preset"}

def register(question, text, source):
    if source not in ("bipia_question", "demo_preset"):
        raise ValueError("Invalid task source")
    token = secrets.token_urlsafe(24)
    with LOCK:
        CONTEXTS[token] = (question, hashlib.sha256(text.encode()).hexdigest(), source)
        while len(CONTEXTS) > MAX_CONTEXTS:
            CONTEXTS.popitem(last=False)
    return {"task_context": token, "intent": description(question, source)}

def resolve(question, text, token=""):
    if not isinstance(question, str) or not isinstance(token, str):
        raise ValueError("question and task_context must be strings")
    if question.strip():
        return description(question.strip(), "user_input")
    if not token:
        return description("", "missing")
    with LOCK:
        context = CONTEXTS.get(token)
    if context is None:
        raise ValueError("Task context expired or invalid; reload the example or enter the real user task")
    actual_question, content_hash, source = context
    if hashlib.sha256(text.encode()).hexdigest() != content_hash:
        raise ValueError("Content changed; reload the example or enter the real user task")
    return description(actual_question, source)
