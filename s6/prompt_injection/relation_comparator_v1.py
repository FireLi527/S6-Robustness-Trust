"""Deterministic task-vs-content authorization comparator over v3 extractions; never grants tools.

Verb groups use only operations seen in v3 TRAINING references; unseen verbs are left
unmatched on purpose so held-out evaluation measures lexical generalization honestly.
"""
GROUPS = (
    frozenset({"删除", "清空", "去掉", "移除", "取消"}),
    frozenset({"修改", "改", "调整", "设为", "设置", "修复", "替换", "覆盖", "重写"}),
    frozenset({"切换", "改用", "提升", "扩大"}),
    frozenset({"创建", "生成", "构建"}),
    frozenset({"写", "写入", "写出", "保存", "复制"}),
    frozenset({"发送", "发出", "发布", "给", "给出", "回复", "告诉", "贴"}),
    frozenset({"读取", "查看", "查询", "访问", "加载", "获取", "下载", "阅读"}),
    frozenset({"运行", "执行", "调用", "使用", "用", "处理", "做", "启动", "启用"}),
    frozenset({"重试", "再试"}),
)
BENIGN = frozenset({"检查", "核对", "校验", "验证", "确认", "测试", "比较", "查看", "查询", "阅读", "评阅", "解释",
                    "计算", "列出", "列", "报告", "显示", "展示", "停止", "结束", "等待", "记录", "提出", "回复"})
CHECKS = frozenset({"检查", "核对", "校验", "验证", "确认", "测试", "比较"})
BROADENING = ("整个", "全部", "所有", "任何")
ACTIVE = frozenset({"execute", "simulation", "unknown"})


def op_score(a: str, b: str) -> int:
    if a == b:
        return 2
    if a in b or b in a or any(a in g and b in g for g in GROUPS):
        return 1
    return 0


def texts(action: dict) -> list[str]:
    return [b["text"] for b in action["bindings"] if b["text"]]


STOP_BIGRAMS = frozenset({"其他", "测试", "演示", "本地", "合成"})


OBJECT_ROLES = frozenset({"object", "data", "destination", "source", "environment", "resolved_directory"})


def targets(action: dict) -> list[str]:
    return [b["text"] for b in action["bindings"] if b["text"] and b["role"] in OBJECT_ROLES]


def overlaps(a: list[str], b: list[str]) -> bool:
    """Containment, or a shared non-generic two-CJK-character span; literal, not semantic."""
    for x in a:
        for y in b:
            if x in y or y in x:
                return True
            for i in range(len(x) - 1):
                pair = x[i:i + 2]
                if pair.isascii() or not all(ord(c) > 0x2E7F for c in pair) or pair in STOP_BIGRAMS:
                    continue
                if pair in y:
                    return True
    return False


def scored(action: dict, task: dict, prohibited: bool) -> tuple:
    """Best (verb score, object overlap) and task action of one polarity; verb score 0 means none."""
    options = [((op_score(action["operation"], t["operation"]), overlaps(texts(action), texts(t))), t)
               for t in task["actions"] if (t["kind"] == "prohibited") == prohibited and t["kind"] != "quoted"]
    options = [o for o in options if o[0][0] > 0]
    return max(options, key=lambda o: o[0]) if options else ((0, False), None)


def violation(action: dict, task: dict) -> bool:
    """Forbidden verb match not outranked by an allowed match, or a modifying verb on a forbidden object."""
    (allowed_score, _), (forbidden_score, forbidden) = scored(action, task, False), scored(action, task, True)
    on_forbidden = any(overlaps(targets(action), targets(t)) for t in task["actions"] if t["kind"] == "prohibited")
    on_allowed = any(overlaps(targets(action), targets(t)) for t in task["actions"] if t["kind"] != "prohibited")
    if forbidden is not None and forbidden_score >= allowed_score:
        if overlaps(texts(action), texts(forbidden)) or (forbidden_score[0] == 2 and not texts(forbidden)) or (not on_allowed and (
                not texts(forbidden) or forbidden_score[0] == 2 or allowed_score[0] == 0)):
            return True
    return action["operation"] not in BENIGN and on_forbidden and not on_allowed


def check_allowed(action: dict, allowed: dict, previous: list, hard: list, soft: list) -> None:
    """Scope widening and redirection are explicit; a missing gate is only a soft signal."""
    op = action["operation"]
    wider = [w for w in BROADENING if any(w in t for t in texts(action)) and not any(w in t for t in texts(allowed))]
    destinations = [b["text"] for b in allowed["bindings"] if b["role"] == "destination" and b["text"]]
    resolved = [b["text"] for b in action["bindings"] if b["role"] == "resolved_directory" and b["text"]]
    if wider:
        hard.append(f"broadened:{op}:{wider[0]}")
    elif destinations and resolved and not overlaps(resolved, destinations):
        hard.append(f"redirected:{op}")
    elif allowed["conditions"] and not overlaps(action["conditions"], allowed["conditions"]) \
            and not (CHECKS & set(previous)):
        soft.append(f"ungated:{op}")


def decide(task: dict, content: dict) -> dict:
    """RISK on explicit violation > UNKNOWN on missing/unmapped > RISK on unauthorized/ungated > NORMAL."""
    hard, soft = [], []
    unknown = list(content["missing_context"])
    unknown += [f"unmapped:{b['text']}" for a in content["actions"] for b in a["bindings"] if b["status"] == "unmapped"]
    unknown += [f"unknown-kind:{a['operation']}" for a in content["actions"] if a["kind"] == "unknown"]
    supported = [t for t in task["actions"] if t["kind"] != "prohibited"]
    previous = []
    for action in content["actions"]:
        if action["kind"] not in ACTIVE:
            continue
        op = action["operation"]
        unmapped = any(b["status"] == "unmapped" for b in action["bindings"])
        allowed = scored(action, task, False)[1]
        if violation(action, task):
            (soft if unmapped else hard).append(f"prohibited:{op}")
        elif allowed is not None:
            check_allowed(action, allowed, previous, hard, soft)
        elif op not in BENIGN and not any(overlaps(texts(action), texts(t)) for t in supported):
            soft.append(f"unauthorized:{op}")
        previous.append(op)
    decision = "RISK" if hard else "UNKNOWN" if unknown else "RISK" if soft else "NORMAL"
    return {"decision": decision, "hard": hard, "unknown": unknown, "soft": soft, "tool_authorization": "not_granted"}
