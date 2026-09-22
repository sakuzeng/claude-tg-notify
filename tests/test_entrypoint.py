"""入口子进程测试：垫片与模块入口都要能在不安装的情况下跑起来。

这是拆包之后最容易悄悄坏掉的一环 —— 单元测试直接 import 包，发现不了 sys.path 问题。
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ROOT, BaseCase, child_env, config, state  # noqa: E402

SHIM = ROOT / "claude-tg-notify"


def run(args, stdin="", env=None):
    return subprocess.run([sys.executable, str(SHIM)] + args, input=stdin,
                          capture_output=True, text=True, timeout=60, env=env or child_env())


class ShimTests(BaseCase):
    def test_shim_exists_and_is_executable(self):
        self.assertTrue(SHIM.exists())
        self.assertTrue(SHIM.stat().st_mode & 0o111, "垫片需要可执行位，README 里是 ./claude-tg-notify")

    def test_version(self):
        from claude_tg_notify import VERSION
        proc = run(["--version"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(VERSION, proc.stdout)

    def test_help_lists_all_subcommands(self):
        proc = run(["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for cmd in ("setup", "install", "uninstall", "test", "status", "hook"):
            self.assertIn(cmd, proc.stdout)

    def test_no_args_prints_help(self):
        self.assertEqual(run([]).returncode, 0)

    def test_hook_writes_state_and_stays_silent(self):
        sid = "entrypoint-test-1"
        payload = json.dumps({"session_id": sid, "cwd": "/tmp/p",
                              "hook_event_name": "UserPromptSubmit", "message": "hello"})
        proc = run(["hook"], stdin=payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "", "非 PermissionRequest 事件绝不能往 stdout 写东西")
        self.assertTrue(state.load_state(sid)["started_at"])

    def test_hook_survives_garbage_input(self):
        for bad in ("{not json", "", "null", "[]"):
            proc = run(["hook"], stdin=bad)
            self.assertEqual(proc.returncode, 0, bad)
            self.assertEqual(proc.stdout, "")

    def test_hook_with_no_start_record_is_silent(self):
        payload = json.dumps({"session_id": "never-started", "cwd": "/tmp/p",
                              "hook_event_name": "Stop", "last_assistant_message": "x"})
        proc = run(["hook"], stdin=payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_install_print_only_emits_valid_hook_json(self):
        proc = run(["install", "--print"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        hooks = json.loads(proc.stdout)["hooks"]
        self.assertEqual(set(hooks), {"UserPromptSubmit", "Stop", "Notification",
                                      "PermissionRequest", "PermissionDenied"})
        for entries in hooks.values():
            for entry in entries:
                for h in entry["hooks"]:
                    self.assertIn("claude", h["command"])


class ModuleEntryTests(BaseCase):
    def test_python_m_works(self):
        from claude_tg_notify import VERSION
        proc = subprocess.run([sys.executable, "-m", "claude_tg_notify", "--version"],
                              capture_output=True, text=True, timeout=60, env=child_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(VERSION, proc.stdout)


if __name__ == "__main__":
    unittest.main()
