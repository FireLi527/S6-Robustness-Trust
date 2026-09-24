"""Content-only live intent inference, separate from trusted task resolution."""
from functools import lru_cache
import threading
from intent_comparison import PROTOTYPES, LABELS, MODEL_CACHE, predict_intent
from semantic_detector import embed_texts

LOCK = threading.Lock()
TASKS_ZH = {
    "read_email": "阅读邮件，概括与用户相关的信息。",
    "search_documents": "审阅检索到的文档，查找与用户文档搜索相关的信息。",
    "create_calendar_event": "审阅会议记录，概括建议的日程安排和后续事项。",
    "send_email": "审阅邮件往来，概括沟通请求和后续事项。",
    "delete_records": "审阅记录管理请求，解释建议的变更。",
    "access_secret": "审阅访问请求，概括其声明的目的和范围。",
}

@lru_cache(maxsize=128)
def infer_content(text):
    with LOCK:
        embeddings = embed_texts([text, *PROTOTYPES.values()], MODEL_CACHE)
        result = predict_intent(text, embeddings)
    return {**result, "name": LABELS[result["label"]],
            "task": {"zh": TASKS_ZH[result["label"]], "en": result["question"]},
            "source": "content_only", "affects_live_policy": False,
            "similarity_is_probability": False}
