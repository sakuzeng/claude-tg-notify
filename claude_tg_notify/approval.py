"""在 Telegram 上批准 / 拒绝工具调用。

这是全项目最微妙的一块，单独成模块。难点是 Telegram 的 getUpdates 只允许一个消费者：
多个会话可能同时在等按钮，谁拿到 poll.lock 谁去拉更新，把拉到的每条点击**按它自带的
请求 id** 写进 inbox，其他会话只盯自己的 inbox 文件。这样谁拉都行，点击不会互相吞掉。
"""

import html
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from . import config, state, telegram

#: callback_data 形如 "p:<请求 id>:<a|s|d>"，分别是允许一次 / 始终允许 / 拒绝。
CALLBACK_PREFIX = "p"
CHOICE_LABELS = {"a": "已允许", "s": "已允许（始终）", "d": "已拒绝"}

#: 锁多久没更新算陈旧（持锁的 hook 被杀掉时）。
LOCK_STALE_SECONDS = 45
#: inbox 里多久没人认领就清掉（迟到的点击）。
INBOX_STALE_SECONDS = 600


# ---------------------------------------------------------------------------
# getUpdates offset
# ---------------------------------------------------------------------------

def read_offset() -> Optional[int]:
    try:
        return int(config.OFFSET_PATH.read_text().strip())
    except Exception:
        return None


def write_offset(value: int) -> None:
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        config.OFFSET_PATH.write_text(str(value))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# inbox
# ---------------------------------------------------------------------------

def inbox_path(req: str) -> "Any":
    return config.INBOX_DIR / (req + ".json")


def read_inbox(req: str) -> Optional[Dict[str, Any]]:
    """取走并删除某个请求的决定。没有就返回 None。"""
    try:
        path = inbox_path(req)
        data = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
        return data
    except Exception:
        return None


def write_inbox(req: str, decision: Dict[str, Any]) -> None:
    try:
        config.INBOX_DIR.mkdir(parents=True, exist_ok=True)
        inbox_path(req).write_text(json.dumps(decision), encoding="utf-8")
    except Exception as exc:
        config.log("inbox write failed: %s" % exc)


def sweep_inbox(max_age: float = INBOX_STALE_SECONDS) -> None:
    """丢掉没人认领的决定：对应的 hook 早已放弃等待。"""
    try:
        now = time.time()
        for f in config.INBOX_DIR.glob("*.json"):
            if now - f.stat().st_mtime > max_age:
                f.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 轮询锁
# ---------------------------------------------------------------------------

def acquire_poll_lock() -> bool:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(config.POLL_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - config.POLL_LOCK.stat().st_mtime > LOCK_STALE_SECONDS:
                    config.POLL_LOCK.unlink()
                    continue
            except FileNotFoundError:
                continue
            return False
    return False


def release_poll_lock() -> None:
    try:
        config.POLL_LOCK.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 拉取与等待
# ---------------------------------------------------------------------------

def poll_callbacks_once(cfg: Dict[str, Any], long_poll: int = 3) -> None:
    """拉一批按钮点击，按各自的请求 id 归档。调用前应持有 poll.lock。"""
    payload: Dict[str, Any] = {"timeout": long_poll, "allowed_updates": ["callback_query"]}
    offset = read_offset()
    if offset is not None:
        payload["offset"] = offset
    updates = telegram.tg_api(cfg, "getUpdates", payload, timeout=long_poll + 10) or []
    allowed = config.allowed_user_ids(cfg)
    sweep_inbox()
    for upd in updates:
        write_offset(int(upd.get("update_id", 0)) + 1)
        cq = upd.get("callback_query") or {}
        parts = str(cq.get("data") or "").split(":")
        if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
            continue
        _, req, choice = parts
        sender = cq.get("from") or {}
        sender_id = str(sender.get("id", ""))
        answer: Dict[str, Any] = {"callback_query_id": cq.get("id")}
        if sender_id not in allowed:
            answer["text"] = "无权操作"
            config.log("rejected callback from user %s" % sender_id)
        else:
            answer["text"] = CHOICE_LABELS.get(choice, "收到")
            write_inbox(req, {
                "choice": choice,
                "from": sender.get("username") or sender.get("first_name") or sender_id,
                "at": time.time(),
            })
        try:
            telegram.tg_api(cfg, "answerCallbackQuery", answer, timeout=10)
        except Exception as exc:
            config.log("answerCallbackQuery failed: %s" % exc)


def wait_for_decision(cfg: Dict[str, Any], req: str, deadline: float,
                      abort_on_mac_touch: bool) -> Optional[Dict[str, Any]]:
    """等到 req 的决定、或到期、或人回到 Mac 前。返回 None 表示到期。"""
    while time.time() < deadline:
        found = read_inbox(req)
        if found:
            return found
        if abort_on_mac_touch:
            idle = config.mac_idle_seconds()
            if idle is not None and idle < 3:
                return {"choice": "terminal"}
        if acquire_poll_lock():
            try:
                poll_callbacks_once(cfg, long_poll=3)
            except Exception as exc:
                # 不推进 offset，Telegram 会重发，点击不会丢。
                config.log("poll failed: %s" % exc)
                time.sleep(2)
            finally:
                release_poll_lock()
        else:
            time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# hook 入口
# ---------------------------------------------------------------------------

def build_keyboard(req: str, has_suggestions: bool) -> Dict[str, Any]:
    rows = [[{"text": "✅ 允许一次", "callback_data": "%s:%s:a" % (CALLBACK_PREFIX, req)},
             {"text": "⛔ 拒绝", "callback_data": "%s:%s:d" % (CALLBACK_PREFIX, req)}]]
    if has_suggestions:
        rows.append([{"text": "✅ 始终允许（不再询问）", "callback_data": "%s:%s:s" % (CALLBACK_PREFIX, req)}])
    return {"inline_keyboard": rows}


def handle_permission_request(cfg: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """发带按钮的消息并等决定。

    返回 hook 输出（decision），或 None 表示交回 Claude Code 的正常权限提示。
    """
    approve = cfg.get("approve") or {}
    if not approve.get("enabled", True) or data.get("agent_id"):
        return None

    sid = data.get("session_id", "")
    st = state.load_state(sid)

    # 人就在 Mac 前：同步 hook 会挡住终端提示，直接让位。
    skip_active = float(approve.get("skip_if_mac_active_seconds") or 0)
    if skip_active > 0:
        idle = config.mac_idle_seconds()
        if idle is not None and idle < skip_active:
            config.log("approve: Mac active %.0fs ago, leaving the prompt to the terminal" % idle)
            return None

    if not config.allowed_user_ids(cfg):
        config.log("approve: group chat without allowed_user_ids; set it in config")
        return None

    req = uuid.uuid4().hex[:12]
    wait = float(approve.get("wait_seconds") or 90)
    suggestions = [s for s in (data.get("permission_suggestions") or []) if isinstance(s, dict)]
    base = "🔔 <b>需要你批准</b>\n%s\n\n%s" % (
        telegram.describe_session(data, st),
        telegram.tool_summary(data.get("tool_name", ""), data.get("tool_input")))
    text = base + "\n\n<i>%d 秒内未响应将交回终端处理</i>" % int(wait)

    mid = telegram.send_message(cfg, text, "permission_prompt",
                                reply_markup=build_keyboard(req, bool(suggestions)))
    if mid is None:
        return None

    # 让随后的 Notification(permission_prompt) 不再发一条无按钮的重复消息。
    st["perm_handled_until"] = time.time() + wait + 20
    state.mark_sent(st, "permission_prompt")
    state.save_state(sid, st)
    config.log("approve: asked for %s (%s, req %s)" % (sid[:8], data.get("tool_name"), req))

    found = wait_for_decision(cfg, req, time.time() + wait, abort_on_mac_touch=skip_active > 0)
    choice = (found or {}).get("choice")
    who = html.escape(str((found or {}).get("from") or ""))

    if choice in ("a", "s"):
        always = choice == "s" and bool(suggestions)
        telegram.edit_message(cfg, mid, base + "\n\n✅ <b>已允许%s</b>（%s，来自 Telegram）"
                              % ("，不再询问" if always else "", who))
        decision: Dict[str, Any] = {"behavior": "allow"}
        if always:
            session_scoped = [s for s in suggestions if s.get("destination") == "session"]
            decision["updatedPermissions"] = session_scoped or suggestions[:1]
        config.log("approve: allowed (%s) by %s" % (choice, who))
    elif choice == "d":
        telegram.edit_message(cfg, mid, base + "\n\n⛔ <b>已拒绝</b>（%s，来自 Telegram）" % who)
        decision = {"behavior": "deny", "message": "用户在 Telegram 上拒绝了这个操作"}
        config.log("approve: denied by %s" % who)
    else:
        reason = "检测到你在 Mac 前" if choice == "terminal" else "未响应"
        telegram.edit_message(cfg, mid, base + "\n\n⌛ <i>%s，请在终端或 Claude App 里处理</i>" % reason)
        config.log("approve: handed back to terminal for %s (%s)" % (sid[:8], reason))
        return None

    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
