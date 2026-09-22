"""路径、日志、配置文件与系统探测。

这里是"从磁盘或系统读到的事实"，不含任何策略判断。
路径全部可被环境变量覆盖，测试据此把整棵树挪进临时目录。
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from . import APP  # noqa: F401  （供子命令打印用）

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(os.environ.get("CLAUDE_TG_NOTIFY_CONFIG_DIR", "~/.config/claude-tg-notify")).expanduser()
CONFIG_PATH = CONFIG_DIR / "config.json"

STATE_DIR = Path(os.environ.get("CLAUDE_TG_NOTIFY_STATE_DIR", "~/.cache/claude-tg-notify")).expanduser()
SESSIONS_DIR = STATE_DIR / "sessions"
INBOX_DIR = STATE_DIR / "inbox"
LOG_PATH = STATE_DIR / "notify.log"
POLL_LOCK = STATE_DIR / "poll.lock"
OFFSET_PATH = STATE_DIR / "updates_offset"

SETTINGS_PATH = Path(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")).expanduser() / "settings.json"

#: 仓库根目录下的命令行入口（git clone 直跑时 hook 指向它）。
SHIM_PATH = Path(__file__).resolve().parent.parent / "claude-tg-notify"


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    """写一行日志。永不抛异常 —— hook 里任何路径都可能调它。"""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "bot_token": "",
    "chat_id": "",
    "proxy": "",
    "min_turn_seconds": 60,
    "min_interval_seconds": 30,
    "max_text_chars": 700,
    "skip_if_mac_active_seconds": 0,
    "allowed_user_ids": [],
    "events": {
        "stop": True,
        "permission_prompt": True,
        "elicitation_dialog": True,
        "agent_needs_input": True,
        "idle_prompt": False,
        "permission_denied": False,
    },
    "silent": {},
    "approve": {
        "enabled": True,
        "wait_seconds": 90,
        "skip_if_mac_active_seconds": 60,
    },
}

#: 这三个子表按键合并，其余键整体覆盖。
_MERGED_TABLES = ("events", "approve", "silent")


def load_config() -> Dict[str, Any]:
    """读配置，缺的键取默认值。文件损坏时退回全默认并记一行日志。"""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except Exception as exc:
        log("config unreadable: %s" % exc)
        return cfg
    for key, value in raw.items():
        if key in _MERGED_TABLES and isinstance(value, dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def configured(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("bot_token")) and bool(str(cfg.get("chat_id") or ""))


def allowed_user_ids(cfg: Dict[str, Any]) -> List[str]:
    """允许点按钮的 Telegram 用户 id。

    显式配置优先；否则私聊取 chat_id 本身（私聊的 chat id 就是用户 id）。
    群聊（负数 id）返回空列表，调用方据此整体关闭远程批准。
    """
    ids = [str(x).strip() for x in (cfg.get("allowed_user_ids") or []) if str(x).strip()]
    if ids:
        return ids
    chat = str(cfg.get("chat_id") or "")
    return [chat] if chat and not chat.startswith("-") else []


# ---------------------------------------------------------------------------
# 系统探测
# ---------------------------------------------------------------------------

def mac_idle_seconds() -> "float | None":
    """距上次键鼠输入的秒数。只有 macOS 有；其他平台返回 None（视为不在电脑前）。"""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
            capture_output=True, text=True, timeout=3, check=False,
        ).stdout
        match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        if match:
            return int(match.group(1)) / 1e9
    except Exception:
        return None
    return None
