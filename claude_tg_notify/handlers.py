"""五个 hook 事件的处理与分发。

约束：除 PermissionRequest 外，任何事件都不许往 stdout 写东西 ——
UserPromptSubmit 的 stdout 会被当作上下文塞给模型。
"""

import html
import json
import time
from typing import Any, Dict, Optional

from . import approval, config, state, telegram

NOTIFICATION_HEADERS = {
    "permission_prompt": "🔔 <b>需要你批准</b>",
    "elicitation_dialog": "❓ <b>需要你回答</b>",
    "agent_needs_input": "❓ <b>需要你输入</b>",
    "idle_prompt": "⏳ <b>Claude 在等你</b>",
    "permission_denied": "⛔ <b>自动模式拒绝了一个操作</b>",
}

#: install 写进 settings.json 的 Notification matcher。
NOTIFICATION_MATCHER = "permission_prompt|elicitation_dialog|agent_needs_input|idle_prompt"

#: 一轮的起点超过这么久还没等到 Stop，就当那次 Stop 丢了，重新计时。
STALE_TURN_SECONDS = 6 * 3600


# ---------------------------------------------------------------------------
# UserPromptSubmit
# ---------------------------------------------------------------------------

def handle_user_prompt(cfg: Dict[str, Any], data: Dict[str, Any]) -> None:
    """只写状态文件，不联网。配置没填也能正常工作。

    **起点只记一次。** 这个事件不只在你敲回车时触发 —— 后台任务完成后注入会话的提示、
    排队发出的消息，同样会触发它。无条件重置 `started_at` 会把一轮的耗时缩成最后一小段，
    长任务反而被 `min_turn_seconds` 拦掉（PITFALL 15）。起点由 Stop 负责清空。
    """
    if data.get("agent_id"):
        return
    sid = data.get("session_id", "")
    st = state.load_state(sid)
    now = time.time()
    try:
        started = float(st.get("started_at") or 0)
    except (TypeError, ValueError):
        started = 0.0
    if not started or now - started > STALE_TURN_SECONDS:
        # 没有起点，或上一次 Stop 丢了（进程被杀、/clear 之类），重新计时。
        st["started_at"] = now
    else:
        config.log("turn for %s already running %.0fs, keeping start" % (sid[:8], now - started))
    st["cwd"] = data.get("cwd", "")
    prompt = (data.get("message") or "").strip()
    if prompt and not st.get("first_prompt"):
        st["first_prompt"] = telegram.truncate(prompt, 120)
    state.save_state(sid, st)


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

def resolve_pending_messages(cfg: Dict[str, Any], st: Dict[str, Any]) -> None:
    """把本会话早先的"需要你处理"消息改写成"已处理"。"""
    for item in st.pop("pending_msgs", None) or []:
        telegram.edit_message(cfg, item.get("message_id"), (item.get("text") or "") + "\n\n<i>✔ 已处理</i>")


def handle_stop(cfg: Dict[str, Any], data: Dict[str, Any]) -> None:
    if data.get("agent_id"):
        return
    sid = data.get("session_id", "")
    st = state.load_state(sid)

    # 先无条件消费 started_at 并收尾旧消息，再决定要不要发通知。
    started = st.get("started_at")
    if started:
        st["started_at"] = None
    resolve_pending_messages(cfg, st)
    state.save_state(sid, st)

    if not cfg["events"].get("stop", True):
        return
    if not started:
        # Stop 在 /clear、恢复会话等场合也会触发，没有开始记录就不是一轮真正的对话。
        config.log("skipped stop: no start record for %s" % sid[:8])
        return

    elapsed = time.time() - float(started)
    min_turn = float(cfg.get("min_turn_seconds") or 0)
    if elapsed < min_turn:
        config.log("skipped stop: turn %.0fs < %.0fs" % (elapsed, min_turn))
        return
    if state.should_skip_for_presence(cfg):
        return

    text = "✅ <b>任务完成</b>\n%s\n<b>耗时</b>：%s" % (
        telegram.describe_session(data, st), telegram.fmt_duration(elapsed))
    if cfg.get("show_activity", True):
        activity = telegram.turn_activity(data.get("transcript_path"), float(started))
        if activity:
            text += "\n" + activity

    # minimal 只报"哪个做完了"，正文一概不带 —— 这是默认，也是这个工具的本分。
    style = str(cfg.get("message_style") or "minimal").strip().lower()
    body = telegram.truncate(data.get("last_assistant_message") or "", int(cfg.get("max_text_chars") or 700))
    if body and style != "minimal":
        escaped = html.escape(body)
        text += ("\n\n<blockquote expandable>%s</blockquote>" % escaped
                 if style == "collapsed" else "\n\n" + escaped)

    if telegram.send_message(cfg, text, "stop") is not None:
        state.mark_sent(st, "stop")
        state.save_state(sid, st)
        config.log("sent stop for %s (%.0fs)" % (sid[:8], elapsed))


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

def handle_notification(cfg: Dict[str, Any], data: Dict[str, Any]) -> None:
    kind = data.get("notification_type") or ""
    if kind not in NOTIFICATION_HEADERS:
        return
    if not cfg["events"].get(kind, False):
        return

    sid = data.get("session_id", "")
    st = state.load_state(sid)

    # 带按钮的版本刚发过，不要再发一条无按钮的重复消息。
    if kind == "permission_prompt" and time.time() < float(st.get("perm_handled_until") or 0):
        config.log("skipped permission_prompt: buttons message already sent")
        return
    if state.rate_limited(cfg, st, kind):
        return
    if state.should_skip_for_presence(cfg):
        return

    message = telegram.truncate(data.get("message") or data.get("title") or kind,
                                int(cfg.get("max_text_chars") or 700))
    text = "%s\n%s\n\n%s" % (NOTIFICATION_HEADERS[kind],
                             telegram.describe_session(data, st), html.escape(message))
    mid = telegram.send_message(cfg, text, kind)
    if mid is not None:
        state.mark_sent(st, kind)
        if kind != "idle_prompt":
            state.remember_pending(st, mid, text)
        state.save_state(sid, st)
        config.log("sent %s for %s" % (kind, sid[:8]))


# ---------------------------------------------------------------------------
# PermissionDenied
# ---------------------------------------------------------------------------

def handle_permission_denied(cfg: Dict[str, Any], data: Dict[str, Any]) -> None:
    if not cfg["events"].get("permission_denied", False):
        return
    sid = data.get("session_id", "")
    st = state.load_state(sid)
    if state.rate_limited(cfg, st, "permission_denied") or state.should_skip_for_presence(cfg):
        return
    text = "%s\n%s\n\n%s" % (NOTIFICATION_HEADERS["permission_denied"],
                             telegram.describe_session(data, st),
                             telegram.tool_summary(data.get("tool_name", ""), data.get("tool_input")))
    if telegram.send_message(cfg, text, "permission_denied") is not None:
        state.mark_sent(st, "permission_denied")
        state.save_state(sid, st)
        config.log("sent permission_denied for %s" % sid[:8])


# ---------------------------------------------------------------------------
# 分发
# ---------------------------------------------------------------------------

def run_hook(raw: str) -> Optional[Dict[str, Any]]:
    """永不抛异常。只有 PermissionRequest 会返回内容（写到 stdout 的决定）。"""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        config.log("bad hook input: %s" % exc)
        return None

    event = data.get("hook_event_name", "")
    cfg = config.load_config()

    if event == "UserPromptSubmit":
        handle_user_prompt(cfg, data)
        return None
    if not config.configured(cfg):
        config.log("not configured; run: claude-tg-notify setup")
        return None

    if event == "Stop":
        handle_stop(cfg, data)
    elif event == "Notification":
        handle_notification(cfg, data)
    elif event == "PermissionRequest":
        return approval.handle_permission_request(cfg, data)
    elif event == "PermissionDenied":
        handle_permission_denied(cfg, data)
    else:
        config.log("ignored event %r" % event)
    return None
