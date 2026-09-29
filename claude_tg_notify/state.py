"""每会话状态文件，以及基于它的节流判断。

一个会话一个 JSON，字段：
    started_at          本轮开始时间戳；Stop 消费后置 None
    cwd / first_prompt  用于描述会话
    last_sent           {事件名: 时间戳}，用于同类节流
    pending_msgs        [{message_id, text}]，Stop 时改写成"已处理"
    perm_handled_until  在此之前不再发无按钮版的权限通知
"""

import json
import os
import re
import time
import uuid
from pathlib import Path
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
    tmp = state_path(session_id).with_name(state_path(session_id).name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(state_path(session_id))


def activity_path(session_id: str, turn_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id + "-" + turn_id)
    return config.ACTIVITY_DIR / (safe + ".jsonl")


def record_tool(data: Dict[str, Any]) -> None:
    """PostToolUse 只记工具名与文件名，不保存命令正文或工具结果。"""
    sid = str(data.get("session_id") or "")
    turn_id = str(data.get("turn_id") or "")
    if not sid or not turn_id:
        return
    name = str(data.get("tool_name") or "?")
    inp = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    files = []
    if name == "apply_patch":
        for match in re.finditer(r"^\*\*\* (?:Add|Update|Delete|Move to) File: (.+)$",
                                 str(inp.get("command") or ""), re.MULTILINE):
            files.append(Path(match.group(1)).name)
    elif name in ("Edit", "Write", "MultiEdit", "NotebookEdit") and inp.get("file_path"):
        files.append(Path(str(inp["file_path"])).name)
    item = {"name": name, "id": str(data.get("tool_use_id") or ""), "files": files[:5]}
    try:
        config.ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(activity_path(sid, turn_id)), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as exc:
        config.log("activity write failed: %s" % exc)


def read_tools(session_id: str, turn_id: str) -> "list[Dict[str, Any]]":
    if not session_id or not turn_id:
        return []
    try:
        path = activity_path(session_id, turn_id)
        if path.stat().st_size > 2_000_000:
            return []
        result = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        path.unlink()
        return result
    except FileNotFoundError:
        return []
    except Exception as exc:
        config.log("activity read failed: %s" % exc)
        return []


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


def user_is_away(cfg: Dict[str, Any]) -> bool:
    """Mac 闲置够久 = 你大概不在电脑前。

    `min_turn_seconds` 是拿耗时去**猜**"你可能已经走开了"；这个函数直接测。
    在手机上驱动会话时，54 秒的回答一样需要推送 —— 没有终端可看。
    探测不到空闲时间（非 macOS）时返回 False：宁可沿用阈值，也不要突然开始刷屏。
    """
    threshold = float(cfg.get("away_after_seconds") or 0)
    if threshold <= 0:
        return False
    idle = config.mac_idle_seconds()
    return idle is not None and idle >= threshold


# ---------------------------------------------------------------------------
# 待处理消息
# ---------------------------------------------------------------------------

def remember_pending(state: Dict[str, Any], message_id: Optional[int], text: str) -> None:
    """记下"需要你处理"消息的 id，供 Stop 时改写。只留最近 10 条。"""
    if message_id:
        state.setdefault("pending_msgs", []).append({"message_id": message_id, "text": text})
        state["pending_msgs"] = state["pending_msgs"][-10:]
