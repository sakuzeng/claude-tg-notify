"""Telegram Bot API 调用，以及发出去的文本怎么拼。

跨模块调用一律走模块对象（`telegram.send_message(...)`）而不是 `from .telegram import send_message`，
这样测试只要打一次 `claude_tg_notify.telegram.tg_api` 就覆盖所有调用点。
"""

import html
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

API_ROOT = "https://api.telegram.org"

#: 盲文空白。Telegram 会裁掉消息首尾的普通空白，但不认它是空白，所以能撑出真正的空行。
BLANK_LINE = "⠀"

#: 会改动磁盘的工具，它们的 file_path 才值得放进"做了什么"那一行。
MUTATING_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
ACTIVITY_MAX_TOOLS = 4
ACTIVITY_MAX_FILES = 3


# ---------------------------------------------------------------------------
# 文本
# ---------------------------------------------------------------------------

def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d 小时 %d 分" % (h, m)
    if m:
        return "%d 分 %d 秒" % (m, s)
    return "%d 秒" % s


def tool_summary(tool_name: str, tool_input: Any) -> str:
    """工具调用的简述：工具名 + 最能说明问题的那个参数。"""
    inp = tool_input if isinstance(tool_input, dict) else {}
    if tool_name == "Bash":
        body = inp.get("command") or ""
    elif tool_name in ("Edit", "Write", "Read", "NotebookEdit", "MultiEdit"):
        body = inp.get("file_path") or inp.get("notebook_path") or ""
    elif tool_name in ("WebFetch", "WebSearch"):
        body = inp.get("url") or inp.get("query") or ""
    else:
        try:
            body = json.dumps(inp, ensure_ascii=False) if inp else ""
        except Exception:
            body = str(tool_input)
    name = html.escape(tool_name or "?")
    body = truncate(str(body), 400)
    return "<b>%s</b>\n<pre>%s</pre>" % (name, html.escape(body)) if body else "<b>%s</b>" % name


def session_title(transcript_path: Optional[str]) -> Optional[str]:
    """transcript 里最后一条 custom-title 记录，没有就 None。"""
    if not transcript_path:
        return None
    try:
        path = Path(transcript_path)
        if not path.exists() or path.stat().st_size > 200_000_000:
            return None
        title = None
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"custom-title"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") == "custom-title" and rec.get("customTitle"):
                    title = str(rec["customTitle"])
        return title
    except Exception:
        return None


def _parse_ts(value: Any) -> Optional[float]:
    """transcript 里的 ISO8601（UTC，末尾 Z）转 epoch 秒；解析不了返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def turn_activity(transcript_path: Optional[str], since: float) -> str:
    """本轮用过哪些工具、动过哪些文件，压成一行。

    纯粹读 transcript 文件里已有的 tool_use 记录并计数，**不经过模型，不产生 token**。
    拿不到或这一轮没调过工具时返回空串，调用方据此决定是否加这一行。
    """
    if not transcript_path:
        return ""
    try:
        path = Path(transcript_path)
        if not path.exists() or path.stat().st_size > 200_000_000:
            return ""
    except Exception:
        return ""

    counts: Dict[str, int] = {}
    files: List[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # 先做廉价的子串判断，绝大多数行不用解析 JSON。
                if '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "assistant":
                    continue
                ts = _parse_ts(rec.get("timestamp"))
                if ts is None or ts < since:
                    continue
                message = rec.get("message")
                items = message.get("content") if isinstance(message, dict) else None
                for item in items or []:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    name = str(item.get("name") or "?")
                    counts[name] = counts.get(name, 0) + 1
                    if name in MUTATING_TOOLS:
                        inp = item.get("input") if isinstance(item.get("input"), dict) else {}
                        base = Path(str(inp.get("file_path") or inp.get("notebook_path") or "")).name
                        if base and base not in files:
                            files.append(base)
    except Exception as exc:
        config.log("activity scan failed: %s" % exc)
        return ""

    if not counts:
        return ""
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ["%s×%d" % (n, c) if c > 1 else n for n, c in ranked[:ACTIVITY_MAX_TOOLS]]
    if len(ranked) > ACTIVITY_MAX_TOOLS:
        shown.append("+%d" % (len(ranked) - ACTIVITY_MAX_TOOLS))
    line = "🛠 " + " ".join(shown)
    if files:
        names = files[:ACTIVITY_MAX_FILES]
        if len(files) > ACTIVITY_MAX_FILES:
            names = names + ["+%d" % (len(files) - ACTIVITY_MAX_FILES)]
        line += " · " + " ".join(names)
    return html.escape(line)


def decorate(cfg: Dict[str, Any], text: str) -> str:
    """每条消息共同的外壳：顶部分隔线 + 尾部空行。

    浅色主题下相邻消息挨得太紧，而气泡间距归客户端主题管、bot 改不了；
    能做的只有在消息内部制造边界。两个都可以在配置里关掉。
    """
    sep = str(cfg.get("separator") or "").strip()
    if sep:
        text = "%s\n%s" % (html.escape(sep), text)
    try:
        gap = max(0, min(int(cfg.get("gap_lines") or 0), 5))
    except (TypeError, ValueError):
        gap = 0
    if gap:
        text += "\n" + "\n".join([BLANK_LINE] * gap)
    return text


def describe_session(data: Dict[str, Any], state: Dict[str, Any]) -> str:
    """每条消息开头的两行：会话标题与项目名。"""
    title = session_title(data.get("transcript_path")) or state.get("first_prompt") or ""
    project = Path(data.get("cwd") or state.get("cwd") or "").name or "?"
    short_id = (data.get("session_id") or "")[:8]
    line = "<b>会话</b>：%s" % html.escape(truncate(title, 80)) if title else "<b>会话</b>：(未命名)"
    return "%s\n<b>项目</b>：%s  <code>#%s</code>" % (line, html.escape(project), short_id)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def tg_api(cfg: Dict[str, Any], method: str, payload: Optional[Dict[str, Any]] = None,
           timeout: int = 15) -> Dict[str, Any]:
    """调一次 Bot API。失败抛 RuntimeError，由调用方决定重试与否。"""
    url = "%s/bot%s/%s" % (API_ROOT, cfg["bot_token"], method)
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    handlers: List[Any] = []
    proxy = (cfg.get("proxy") or "").strip()
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"ok": False, "description": "HTTP %s" % exc.code}
    if not body.get("ok"):
        raise RuntimeError("Telegram %s failed: %s" % (method, body.get("description", body)))
    return body.get("result", {})


def send_message(cfg: Dict[str, Any], text: str, kind: str = "",
                 reply_markup: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """发一条消息。返回 message_id（拿不到则 0），失败返回 None。"""
    payload: Dict[str, Any] = {
        "chat_id": cfg["chat_id"],
        "text": decorate(cfg, text),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": bool((cfg.get("silent") or {}).get(kind, False)),
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            result = tg_api(cfg, "sendMessage", payload)
            return int((result or {}).get("message_id") or 0)
        except Exception as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    config.log("send failed: %s" % last_err)
    return None


def edit_message(cfg: Dict[str, Any], message_id: Optional[int], text: str) -> None:
    """改写一条已发出的消息并去掉按钮。尽力而为，失败只记日志。"""
    if not message_id:
        return
    payload: Dict[str, Any] = {
        "chat_id": cfg["chat_id"], "message_id": message_id, "text": decorate(cfg, text),
        "parse_mode": "HTML", "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": []},
    }
    try:
        tg_api(cfg, "editMessageText", payload)
    except Exception as exc:
        config.log("edit failed: %s" % exc)
