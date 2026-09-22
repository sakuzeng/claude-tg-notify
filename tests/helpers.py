"""测试公共设施。

每个测试文件都必须先 import 本模块 —— 它在导入 claude_tg_notify 之前把三个路径环境变量
指向临时目录，保证测试绝不碰真实的 ~/.config、~/.cache 与 ~/.claude。
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="ctn-test-"))
os.environ["CLAUDE_TG_NOTIFY_CONFIG_DIR"] = str(TMP / "config")
os.environ["CLAUDE_TG_NOTIFY_STATE_DIR"] = str(TMP / "state")
os.environ["CLAUDE_CONFIG_DIR"] = str(TMP / "claude")

from claude_tg_notify import approval, cli, config, handlers, install, state, telegram  # noqa: E402

SID = "sess-1234abcd"
USER_ID = 42
CHAT_ID = "42"


def payload(event, **kw):
    """构造一份 hook stdin JSON。"""
    base = {"session_id": SID, "cwd": "/tmp/myproj", "hook_event_name": event}
    base.update(kw)
    return json.dumps(base)


def child_env():
    """子进程用的环境变量，指向同一套临时目录。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    return env


class FakeTelegram:
    """假的 Bot API。

    sendMessage 返回递增的 message_id；getUpdates 吐出预置队列并清空；其余返回空 dict。
    """

    def __init__(self):
        self.calls = []
        self.updates = []
        self.next_id = 100

    def __call__(self, cfg, method, payload=None, timeout=15):
        self.calls.append((method, payload))
        if method == "sendMessage":
            self.next_id += 1
            return {"message_id": self.next_id}
        if method == "getUpdates":
            batch, self.updates = self.updates, []
            return batch
        return {}

    def by(self, method):
        return [p for m, p in self.calls if m == method]

    def sent(self):
        return self.by("sendMessage")

    def edits(self):
        return self.by("editMessageText")

    def answers(self):
        return self.by("answerCallbackQuery")


class BaseCase(unittest.TestCase):
    """打掉所有出网与睡眠，清空状态目录。"""

    def setUp(self):
        self.tg = FakeTelegram()
        self.tg_patch = mock.patch.object(telegram, "tg_api", side_effect=self.tg)
        self.tg_mock = self.tg_patch.start()
        self.addCleanup(self.tg_patch.stop)

        for target, attr, value in ((telegram.time, "sleep", None), (approval.time, "sleep", None)):
            p = mock.patch.object(target, attr, return_value=value)
            p.start()
            self.addCleanup(p.stop)

        # 默认当作"人不在 Mac 前"，需要相反行为的用例自己再 patch。
        p = mock.patch.object(config, "mac_idle_seconds", return_value=None)
        p.start()
        self.addCleanup(p.stop)

        config.save_config({
            "bot_token": "123:abcdefghijklmnopqrstuvwxyz",
            "chat_id": CHAT_ID,
            "min_turn_seconds": 30,
            "min_interval_seconds": 30,
            "approve": {"wait_seconds": 5},
        })
        self.reset_state()

    def reset_state(self):
        for d in (config.SESSIONS_DIR, config.INBOX_DIR):
            if d.exists():
                for f in d.glob("*"):
                    f.unlink()
        for f in (config.POLL_LOCK, config.OFFSET_PATH):
            if f.exists():
                f.unlink()

    def started_seconds_ago(self, seconds, sid=SID):
        """伪造"这一轮在 N 秒前开始"。"""
        st = state.load_state(sid)
        st["started_at"] = time.time() - seconds
        state.save_state(sid, st)
