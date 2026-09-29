"""Codex 四类 hook 的离线端到端测试。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SID, BaseCase, config, handlers, payload, state, telegram  # noqa: E402

TURN = "turn-abc"


class CodexHookTests(BaseCase):
    def prompt(self, text="请修复登录", turn_id=TURN):
        return handlers.run_hook(payload("UserPromptSubmit", turn_id=turn_id, prompt=text))

    def stop(self, turn_id=TURN, body="已完成"):
        return handlers.run_hook(payload("Stop", turn_id=turn_id, last_assistant_message=body))

    def tool(self, name="Bash", command="npm test", call_id="call-1"):
        return handlers.run_hook(payload("PostToolUse", turn_id=TURN, tool_name=name,
                                         tool_use_id=call_id, tool_input={"command": command}))

    def test_codex_prompt_fields_and_same_turn_start(self):
        self.assertIsNone(self.prompt("  修复 <登录>  "))
        self.started_seconds_ago(60)
        started = state.load_state(SID)["started_at"]
        self.prompt("补充说明")
        st = state.load_state(SID)
        self.assertEqual(st["started_at"], started)
        self.assertEqual(st["first_prompt"], "修复 <登录>")
        self.assertEqual(st["turn_id"], TURN)

    def test_new_turn_gets_new_start_and_title(self):
        self.prompt("第一轮")
        self.started_seconds_ago(100)
        old_start = state.load_state(SID)["started_at"]
        self.prompt("第二轮", turn_id="turn-next")
        st = state.load_state(SID)
        self.assertEqual(st["turn_id"], "turn-next")
        self.assertEqual(st["first_prompt"], "第二轮")
        self.assertGreater(st["started_at"], old_start)

    def test_long_turn_sends_minimal_notification(self):
        self.prompt("修 <bug>")
        self.started_seconds_ago(125)
        self.stop(body="正文不应默认转发")
        message = self.tg.sent()[0]["text"]
        self.assertIn("修 &lt;bug&gt;", message)
        self.assertIn("2 分 5 秒", message)
        self.assertIn("myproj", message)
        self.assertNotIn("正文不应默认转发", message)

    def test_short_turn_skipped_unless_user_away(self):
        self.prompt()
        self.tool()
        self.stop()
        self.assertEqual(self.tg.sent(), [])
        self.assertFalse(state.activity_path(SID, TURN).exists())
        self.prompt(turn_id="second")
        with mock.patch.object(config, "mac_idle_seconds", return_value=300):
            self.stop(turn_id="second")
        self.assertEqual(len(self.tg.sent()), 1)

    def test_activity_uses_post_tool_use_not_transcript(self):
        self.prompt()
        self.tool(name="apply_patch", command="*** Begin Patch\n*** Update File: /tmp/a&b.py\n*** End Patch")
        self.assertNotIn("*** Begin Patch", state.activity_path(SID, TURN).read_text())
        self.tool(name="apply_patch", command="ignored", call_id="call-1")
        self.tool(name="Bash", call_id="call-2")
        self.started_seconds_ago(60)
        self.stop()
        message = self.tg.sent()[0]["text"]
        self.assertIn("🛠", message)
        self.assertIn("apply_patch", message)
        self.assertIn("<code>a&amp;b.py</code>", message)
        self.assertFalse(state.activity_path(SID, TURN).exists())

    def test_activity_can_be_disabled(self):
        cfg = config.load_config()
        cfg["show_activity"] = False
        config.save_config(cfg)
        self.prompt()
        self.tool()
        self.started_seconds_ago(60)
        self.stop()
        self.assertNotIn("🛠", self.tg.sent()[0]["text"])

    def test_body_styles(self):
        for style, expected in (("full", "正文 &lt;b&gt;"),
                                ("collapsed", "<blockquote expandable>正文 &lt;b&gt;</blockquote>")):
            cfg = config.load_config()
            cfg["message_style"] = style
            cfg["min_interval_seconds"] = 0
            config.save_config(cfg)
            self.prompt(turn_id=style)
            self.started_seconds_ago(60)
            self.stop(turn_id=style, body="正文 <b>")
            self.assertIn(expected, self.tg.sent()[-1]["text"])

    def test_duplicate_stop_and_mismatched_turn_do_not_send(self):
        self.prompt()
        self.started_seconds_ago(60)
        self.stop(turn_id="other")
        self.assertEqual(self.tg.sent(), [])
        self.stop()
        self.stop()
        self.assertEqual(len(self.tg.sent()), 1)

    def test_completion_is_rate_limited(self):
        self.prompt()
        self.started_seconds_ago(60)
        self.stop()
        self.prompt(turn_id="second")
        self.started_seconds_ago(60)
        self.stop(turn_id="second")
        self.assertEqual(len(self.tg.sent()), 1)

    def test_subagent_and_old_claude_events_ignored(self):
        handlers.run_hook(payload("UserPromptSubmit", turn_id=TURN, prompt="x", agent_id="sub"))
        self.assertEqual(state.load_state(SID), {})
        handlers.run_hook(payload("Notification", notification_type="permission_prompt"))
        handlers.run_hook(payload("PermissionDenied", tool_name="Bash"))
        self.assertEqual(self.tg.sent(), [])

    def test_unconfigured_stop_and_bad_json_are_safe(self):
        self.prompt()
        self.started_seconds_ago(60)
        config.save_config({"bot_token": "", "chat_id": ""})
        self.assertIsNone(self.stop())
        self.assertIsNone(handlers.run_hook("{broken"))
        self.assertEqual(self.tg.calls, [])

    def test_send_failure_is_swallowed(self):
        self.prompt()
        self.started_seconds_ago(60)
        self.tg_mock.side_effect = RuntimeError("network")
        self.assertIsNone(self.stop())

    def test_silent_and_presence_switch(self):
        cfg = config.load_config()
        cfg["silent"] = {"stop": True}
        config.save_config(cfg)
        self.prompt()
        self.started_seconds_ago(60)
        self.stop()
        self.assertTrue(self.tg.sent()[0]["disable_notification"])

    def test_message_shell(self):
        self.prompt()
        self.started_seconds_ago(60)
        self.stop()
        message = self.tg.sent()[0]["text"]
        self.assertTrue(message.startswith("━"))
        self.assertTrue(message.endswith(telegram.BLANK_LINE))


if __name__ == "__main__":
    unittest.main()
