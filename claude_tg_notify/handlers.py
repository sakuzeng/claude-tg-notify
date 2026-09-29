"""Codex hook 事件处理；只有 PermissionRequest 可以输出决定 JSON。"""

import html
import json
import time
from typing import Any, Dict, Optional

from . import approval, config, state, telegram

STALE_TURN_SECONDS = 6 * 3600


def handle_user_prompt(data: Dict[str, Any]) -> None:
    """记录一轮的起点；同一 turn_id 的追加提示不重置耗时。"""
    if data.get("agent_id"):
        return
    sid = str(data.get("session_id") or "")
    turn_id = str(data.get("turn_id") or "")
    st = state.load_state(sid)
    now = time.time()
    try:
        started = float(st.get("started_at") or 0)
    except (TypeError, ValueError):
        started = 0
    new_turn = bool(turn_id and st.get("turn_id") != turn_id)
    if new_turn or not started or now - started > STALE_TURN_SECONDS:
        st["started_at"] = now
        st["turn_id"] = turn_id
    st["cwd"] = data.get("cwd") or st.get("cwd") or ""
    prompt = str(data.get("prompt") or "").strip()
    if prompt and (new_turn or not st.get("first_prompt")):
        st["first_prompt"] = telegram.truncate(prompt, 120)
    state.save_state(sid, st)


def handle_post_tool(data: Dict[str, Any]) -> None:
    if not data.get("agent_id"):
        state.record_tool(data)


def handle_stop(cfg: Dict[str, Any], data: Dict[str, Any]) -> None:
    if data.get("agent_id") or not cfg["events"].get("stop", True):
        return
    sid = str(data.get("session_id") or "")
    turn_id = str(data.get("turn_id") or "")
    st = state.load_state(sid)
    if turn_id and st.get("last_completed_turn_id") == turn_id:
        config.log("skipped stop: duplicate turn %s" % turn_id)
        return
    if turn_id and st.get("turn_id") and st["turn_id"] != turn_id:
        config.log("skipped stop: turn mismatch for %s" % sid[:8])
        return
    started = st.get("started_at")
    if not started:
        config.log("skipped stop: no start record for %s" % sid[:8])
        return
    st["started_at"] = None
    st["last_completed_turn_id"] = turn_id
    state.save_state(sid, st)
    activity_items = state.read_tools(sid, turn_id)

    elapsed = max(0, time.time() - float(started))
    away = state.user_is_away(cfg)
    min_turn = float(cfg.get("min_turn_seconds") or 0)
    if elapsed < min_turn and not away:
        config.log("skipped stop: turn %.0fs < %.0fs" % (elapsed, min_turn))
        return
    if state.rate_limited(cfg, st, "stop"):
        return
    if state.should_skip_for_presence(cfg):
        return

    message = "✅ <b>任务完成</b>\n%s\n<b>耗时</b>：%s" % (
        telegram.describe_session(data, st), telegram.fmt_duration(elapsed))
    if cfg.get("show_activity", True):
        activity = telegram.codex_turn_activity(activity_items)
        if activity:
            message += "\n" + activity
    style = str(cfg.get("message_style") or "minimal").strip().lower()
    body = telegram.truncate(str(data.get("last_assistant_message") or ""),
                             int(cfg.get("max_text_chars") or 700))
    if body and style != "minimal":
        escaped = html.escape(body)
        message += ("\n\n<blockquote expandable>%s</blockquote>" % escaped
                    if style == "collapsed" else "\n\n" + escaped)
    if telegram.send_message(cfg, message, "stop") is not None:
        fresh = state.load_state(sid)
        if fresh.get("last_completed_turn_id") == turn_id:
            state.mark_sent(fresh, "stop")
            state.save_state(sid, fresh)
        config.log("sent stop for %s (%.0fs%s)" % (
            sid[:8], elapsed, "，你不在 Mac 前" if away else ""))


def run_hook(raw: str) -> Optional[Dict[str, Any]]:
    """分发 Codex hook；调用方保证异常不影响 Codex。"""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        config.log("bad hook input: %s" % exc)
        return None
    event = data.get("hook_event_name")
    if event == "UserPromptSubmit":
        handle_user_prompt(data)
        return None
    if event == "PostToolUse":
        handle_post_tool(data)
        return None
    cfg = config.load_config()
    if not config.configured(cfg):
        config.log("not configured; run: codex-tg-notify setup")
        return None
    if event == "Stop":
        handle_stop(cfg, data)
    elif event == "PermissionRequest":
        return approval.handle_permission_request(cfg, data)
    else:
        config.log("ignored event %r" % event)
    return None
