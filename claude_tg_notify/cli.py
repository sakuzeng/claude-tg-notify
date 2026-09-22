"""命令行门面：解析参数、调用各模块、把结果打印给人看。

只有本模块与 __main__ 允许 print —— 其余模块的 stdout 会被 Claude Code 当作数据。
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import APP, VERSION, approval, config, handlers, install, telegram


def cmd_setup(args: argparse.Namespace) -> int:
    cfg = config.load_config()
    token = args.token or ""
    if not token:
        print("1) 在 Telegram 里找 @BotFather，发送 /newbot，按提示取名，拿到形如 123456:ABC-DEF... 的 token。")
        token = input("2) 粘贴 bot token: ").strip()
    if not re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", token):
        print("token 格式不对，应形如 123456789:AAxxxxxxxx", file=sys.stderr)
        return 2
    cfg["bot_token"] = token
    if args.proxy is not None:
        cfg["proxy"] = args.proxy

    try:
        me = telegram.tg_api(cfg, "getMe")
    except Exception as exc:
        print("连不上 Telegram API：%s\n如果在国内，给 --proxy http://127.0.0.1:7890 或先开系统代理。" % exc,
              file=sys.stderr)
        return 1
    print("bot 验证通过：@%s" % me.get("username"))

    chat_id = str(args.chat_id or "").strip()
    if not chat_id:
        chat_id = _discover_chat_id(cfg, me.get("username"))
        if not chat_id:
            return 1

    cfg["chat_id"] = chat_id
    config.save_config(cfg)
    print("配置已写入 %s" % config.CONFIG_PATH)

    if not config.allowed_user_ids(cfg):
        print("⚠ 这是一个群聊 chat id。远程批准默认关闭，需要在配置里填 allowed_user_ids "
              "（允许点按钮的 Telegram 用户 id）才会启用。")

    ok = telegram.send_message(
        cfg, "✅ <b>claude-tg-notify 已连接</b>\n之后 Claude Code 的任务完成 / 需要确认会推到这里。") is not None
    print("测试消息：%s" % ("已发送，看手机" if ok else "发送失败，查看 %s" % config.LOG_PATH))
    if not all(install.hooks_installed(config.SETTINGS_PATH).values()):
        print("下一步：claude-tg-notify install")
    return 0 if ok else 1


def _discover_chat_id(cfg: Dict[str, Any], bot_username: Optional[str]) -> str:
    """等用户给 bot 发一条消息，从中取 chat id。"""
    print("3) 现在在 Telegram 里打开 @%s，点 Start 或随便发一条消息；我在这里等 90 秒…" % bot_username)
    deadline = time.time() + 90
    offset = None
    chat_id = ""
    while time.time() < deadline and not chat_id:
        payload: Dict[str, Any] = {"timeout": 20, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        try:
            updates = telegram.tg_api(cfg, "getUpdates", payload, timeout=30)
        except Exception as exc:
            print("getUpdates 失败：%s" % exc, file=sys.stderr)
            time.sleep(2)
            continue
        for upd in updates or []:
            offset = int(upd.get("update_id", 0)) + 1
            chat = (upd.get("message") or {}).get("chat") or {}
            if chat.get("id") is not None:
                chat_id = str(chat["id"])
                who = chat.get("username") or chat.get("title") or chat.get("first_name") or ""
                print("收到来自 %s 的消息，chat_id = %s" % (who, chat_id))
    if offset is not None:
        approval.write_offset(offset)   # 别让这些消息再被批准轮询拉一遍
    if not chat_id:
        print("90 秒内没收到消息。给 bot 发一条后重新运行 setup，或直接用 --chat-id 指定。", file=sys.stderr)
    return chat_id


def cmd_test(args: argparse.Namespace) -> int:
    cfg = config.load_config()
    if not config.configured(cfg):
        print("还没配置，先运行 setup。", file=sys.stderr)
        return 2

    if args.approve:
        # 真实发到 Telegram 的批准演练，走的就是 hook 那条代码路径。
        fake = {
            "session_id": "test-approve", "cwd": os.getcwd(), "hook_event_name": "PermissionRequest",
            "tool_name": "Bash", "tool_input": {"command": "echo '这是一次远程批准演练'"},
            "permission_suggestions": [{"type": "addRules", "behavior": "allow", "destination": "session",
                                        "rules": [{"toolName": "Bash", "ruleContent": "echo *"}]}],
        }
        cfg["approve"]["skip_if_mac_active_seconds"] = 0   # 演练时人就在电脑前，别让位
        print("已发送带按钮的消息，在手机上点一下（最多等 %ss）…" % cfg["approve"].get("wait_seconds"))
        out = approval.handle_permission_request(cfg, fake)
        print("结果：%s" % (json.dumps(out, ensure_ascii=False) if out else "未响应/交回终端"))
        return 0

    text = args.text or "🧪 <b>测试消息</b>\n来自 %s，%s" % (APP, time.strftime("%Y-%m-%d %H:%M:%S"))
    ok = telegram.send_message(cfg, text) is not None
    print("已发送" if ok else "发送失败，见 %s" % config.LOG_PATH)
    return 0 if ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config.load_config()
    token = cfg.get("bot_token") or ""
    masked = (token[:6] + "…" + token[-4:]) if len(token) > 12 else ("(未设置)" if not token else "***")
    ap = cfg.get("approve") or {}

    print("%s %s" % (APP, VERSION))
    print("包路径    : %s" % Path(__file__).resolve().parent)
    print("hook 命令 : %s" % install.hook_command())
    print("配置文件  : %s%s" % (config.CONFIG_PATH, "" if config.CONFIG_PATH.exists() else "  (不存在)"))
    print("bot token : %s" % masked)
    print("chat id   : %s" % (cfg.get("chat_id") or "(未设置)"))
    print("proxy     : %s" % (cfg.get("proxy") or "(直连)"))
    print("阈值      : 任务耗时 ≥ %ss 才推送；同类通知间隔 ≥ %ss；Mac 活跃跳过 = %ss" % (
        cfg.get("min_turn_seconds"), cfg.get("min_interval_seconds"), cfg.get("skip_if_mac_active_seconds")))
    print("事件      : %s" % ", ".join("%s=%s" % (k, "on" if v else "off") for k, v in cfg["events"].items()))
    print("远程批准  : %s；等待 %ss；Mac %ss 内活跃则交回终端；可操作用户 %s" % (
        "on" if ap.get("enabled", True) else "off", ap.get("wait_seconds"),
        ap.get("skip_if_mac_active_seconds"),
        ", ".join(config.allowed_user_ids(cfg)) or "(无！群聊需设置 allowed_user_ids)"))

    inst = install.hooks_installed(config.SETTINGS_PATH)
    print("hooks     : %s" % ", ".join("%s=%s" % (k, "✓" if v else "✗") for k, v in inst.items()))
    print("            (%s)" % config.SETTINGS_PATH)
    warning = install.stale_timeout_warning(cfg, config.SETTINGS_PATH)
    if warning:
        print(warning)

    if config.LOG_PATH.exists():
        print("最近日志  :")
        for line in config.LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]:
            print("  " + line)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    if args.print_only:
        print(json.dumps({"hooks": install.our_hook_entries()}, ensure_ascii=False, indent=2))
        return 0
    try:
        backup = install.install_hooks(config.SETTINGS_PATH)
    except json.JSONDecodeError as exc:
        print("%s 不是合法 JSON，先修好它：%s" % (config.SETTINGS_PATH, exc), file=sys.stderr)
        return 1
    print("hooks 已写入 %s" % config.SETTINGS_PATH)
    print("hook 命令 : %s" % install.hook_command())
    if backup:
        print("备份     : %s" % backup)
    print("正在运行的 Claude Code 会话需要重启（或在里面执行一次 /hooks）才会加载新 hook。")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    backup = install.uninstall_hooks(config.SETTINGS_PATH)
    print("已移除 hooks" if backup else "settings.json 里没有本工具的 hooks")
    if backup:
        print("备份     : %s" % backup)
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Claude Code 调用的入口。任何异常都吞掉并返回 0，绝不打断会话。"""
    try:
        out = handlers.run_hook(sys.stdin.read())
        if out:
            sys.stdout.write(json.dumps(out))
            sys.stdout.flush()
    except Exception as exc:
        config.log("hook crashed: %r" % exc)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP, description="把 Claude Code 的会话事件推到 Telegram，并可在 Telegram 上批准工具调用。")
    parser.add_argument("--version", action="version", version="%s %s" % (APP, VERSION))
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("setup", help="首次配置：bot token + chat id")
    p.add_argument("--token", help="bot token（不给则交互输入）")
    p.add_argument("--chat-id", help="跳过自动探测，直接指定 chat id")
    p.add_argument("--proxy", help="HTTP 代理，如 http://127.0.0.1:7890")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("test", help="发一条测试消息")
    p.add_argument("--text")
    p.add_argument("--approve", action="store_true", help="演练一次带按钮的远程批准（真实发到 Telegram）")
    p.set_defaults(func=cmd_test)

    sub.add_parser("status", help="查看配置与 hook 状态").set_defaults(func=cmd_status)

    p = sub.add_parser("install", help="把 hooks 写进 ~/.claude/settings.json")
    p.add_argument("--print", dest="print_only", action="store_true", help="只打印 JSON，不写文件")
    p.set_defaults(func=cmd_install)

    sub.add_parser("uninstall", help="从 settings.json 移除 hooks").set_defaults(func=cmd_uninstall)
    sub.add_parser("hook", help="hook 入口（Claude Code 调用）").set_defaults(func=cmd_hook)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    return int(args.func(args) or 0)
