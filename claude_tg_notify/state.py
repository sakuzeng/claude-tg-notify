"""每会话状态文件，以及基于它的节流判断。

一个会话一个 JSON，字段：
    started_at          本轮开始时间戳；Stop 消费后置 None
    cwd / first_prompt  用于描述会话
    last_sent           {事件名: 时间戳}，用于同类节流
    pending_msgs        [{message_id, text}]，Stop 时改写成"已处理"
    perm_handled_until  在此之前不再发无按钮版的权限通知
"""

import json
import re
import time
from typing import Any, Dict, Optional

from . import config


def state_path(session_id: str) -> "Any":
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    return config.SESSIONS_DIR / (safe + ".json")


def load_state(session_id: str) -> Dict[str, Any]:
    try:
        return json.loads(state_path(session_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(session_id: str, state: Dict[str, Any]) -> None:
    """先写临时文件再 replace，同会话的并发 hook 不会读到半截文件。"""
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = state_path(session_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path(session_id))


# ---------------------------------------------------------------------------
# 节流
# ---------------------------------------------------------------------------

def mark_sent(state: Dict[str, Any], kind: str) -> None:
    state.setdefault("last_sent", {})[kind] = time.time()


def rate_limited(cfg: Dict[str, Any], state: Dict[str, Any], kind: str) -> bool:
    interval = float(cfg.get("min_interval_seconds") or 0)
    last = float((state.get("last_sent") or {}).get(kind, 0))
    if interval > 0 and time.time() - last < interval:
        config.log("skipped %s: sent %.0fs ago (< %.0fs)" % (kind, time.time() - last, interval))
        return True
    return False


def should_skip_for_presence(cfg: Dict[str, Any]) -> bool:
    """人就在 Mac 前时是否跳过普通通知。阈值为 0 表示永不跳过。"""
    limit = float(cfg.get("skip_if_mac_active_seconds") or 0)
    if limit <= 0:
        return False
    idle = config.mac_idle_seconds()
    if idle is None:
        return False
    if idle < limit:
        config.log("skipped: Mac active %.0fs ago (< %.0fs)" % (idle, limit))
        return True
    return False


# ---------------------------------------------------------------------------
# 待处理消息
# ---------------------------------------------------------------------------

def remember_pending(state: Dict[str, Any], message_id: Optional[int], text: str) -> None:
    """记下"需要你处理"消息的 id，供 Stop 时改写。只留最近 10 条。"""
    if message_id:
        state.setdefault("pending_msgs", []).append({"message_id": message_id, "text": text})
        state["pending_msgs"] = state["pending_msgs"][-10:]
