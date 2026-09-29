"""把 Codex hook 合并进 ~/.codex/hooks.json。

只碰自己的条目：写入前先按标记剔除旧的再追加，所以重复安装与版本升级都是幂等的，
别人装的 hook 原样保留。
"""

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config

#: 用来认出"这条 hook 是我们装的"。必须覆盖所有历史入口名，否则升级会留下重复条目：
#: claude_tg_notify.py（0.1–0.2 的单文件）、claude-tg-notify（垫片与 console script）、
#: -m claude_tg_notify（pip 安装后的模块入口）。两个标记都足够独特，不会误伤别人的 hook。
HOOK_MARKERS = ("codex_tg_notify", "codex-tg-notify", "claude_tg_notify", "claude-tg-notify")

#: PermissionRequest 是同步 hook，要等用户点按钮，超时须比等待时长留出余量。
TIMEOUT_MARGIN_SECONDS = 30


def hook_command() -> str:
    """hook 里实际执行的命令。

    优先用仓库根目录的垫片配系统 python3 —— hook 跑在裸子 shell 里，PATH 和 venv 都不可靠，
    绝对路径最不容易坏。pip 安装的场景没有垫片，退回用当前解释器的绝对路径调模块入口。
    """
    if config.SHIM_PATH.exists():
        return "python3 '%s' hook" % str(config.SHIM_PATH).replace("'", "'\\''")
    return "'%s' -m claude_tg_notify hook" % str(Path(sys.executable).resolve()).replace("'", "'\\''")


def is_ours(entry: Dict[str, Any]) -> bool:
    for h in entry.get("hooks", []) or []:
        cmd = str(h.get("command", ""))
        if any(marker in cmd for marker in HOOK_MARKERS):
            return True
    return False


def our_hook_entries(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, List[Dict[str, Any]]]:
    cmd = hook_command()
    wait = int(((cfg or config.load_config()).get("approve") or {}).get("wait_seconds") or 90)
    return {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd, "timeout": 10}]}],
        "PostToolUse": [{"hooks": [{"type": "command", "command": cmd, "timeout": 10}]}],
        "Stop": [{"hooks": [{"type": "command", "command": cmd, "timeout": 30, "async": True}]}],
        "PermissionRequest": [{"hooks": [{"type": "command", "command": cmd,
                                          "timeout": wait + TIMEOUT_MARGIN_SECONDS}]}],
    }


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------

def read_settings(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_settings(path: Path, settings: Dict[str, Any]) -> Optional[Path]:
    """原子写，并在覆盖前留一份带时间戳的备份。"""
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        backup.write_bytes(path.read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return backup


def install_hooks(path: Path) -> Optional[Path]:
    settings = read_settings(path)
    before = json.dumps(settings, sort_keys=True)
    hooks = settings.setdefault("hooks", {})
    for event in list(hooks):
        hooks[event] = [e for e in (hooks[event] or []) if not is_ours(e)]
        if not hooks[event]:
            del hooks[event]
    for event, entries in our_hook_entries().items():
        hooks[event] = (hooks.get(event) or []) + entries
    if path.exists() and json.dumps(settings, sort_keys=True) == before:
        return None
    return write_settings(path, settings)


def uninstall_hooks(path: Path) -> Optional[Path]:
    settings = read_settings(path)
    hooks = settings.get("hooks") or {}
    changed = False
    for event in list(hooks.keys()):
        kept = [e for e in hooks[event] if not is_ours(e)]
        if len(kept) != len(hooks[event]):
            changed = True
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks and "hooks" in settings:
        del settings["hooks"]
    return write_settings(path, settings) if changed else None


def hooks_installed(path: Path) -> Dict[str, bool]:
    try:
        hooks = read_settings(path).get("hooks") or {}
    except Exception:
        hooks = {}
    return {event: any(is_ours(e) for e in (hooks.get(event) or [])) for event in our_hook_entries()}


# ---------------------------------------------------------------------------
# 对账
# ---------------------------------------------------------------------------

def installed_permission_timeout(path: Path) -> Optional[int]:
    try:
        for entry in read_settings(path).get("hooks", {}).get("PermissionRequest") or []:
            if is_ours(entry):
                for h in entry.get("hooks", []):
                    if h.get("timeout") is not None:
                        return int(h["timeout"])
    except Exception:
        pass
    return None


def stale_timeout_warning(cfg: Dict[str, Any], path: Path) -> Optional[str]:
    """改了 wait_seconds 却没重装时，hook 会在决定回来之前被 Codex 杀掉。"""
    wait = int((cfg.get("approve") or {}).get("wait_seconds") or 90)
    needed = wait + TIMEOUT_MARGIN_SECONDS
    installed = installed_permission_timeout(path)
    if installed is None or installed >= needed:
        return None
    return ("⚠ approve.wait_seconds=%ss 需要 hook 超时 ≥ %ss，但 hooks.json 里是 %ss。"
            "重新运行 install，否则按钮点了也可能来不及生效。" % (wait, needed, installed))
