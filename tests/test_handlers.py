"""五个事件处理与分发。"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SID, TMP, BaseCase, config, handlers, payload, state, telegram  # noqa: E402


class DispatchTests(BaseCase):
    def test_not_configured_is_silent(self):
        config.save_config({"bot_token": "", "chat_id": ""})
        handlers.run_hook(payload("Stop", last_assistant_message="done"))
        self.assertEqual(self.tg.calls, [])

    def test_bad_input_does_not_raise(self):
        self.assertIsNone(handlers.run_hook("{not json"))
        self.assertIsNone(handlers.run_hook(""))
        self.assertEqual(self.tg.calls, [])

    def test_unknown_event_ignored(self):
        self.assertIsNone(handlers.run_hook(payload("SessionStart")))
        self.assertEqual(self.tg.calls, [])

    def test_send_failure_is_swallowed(self):
        self.tg_mock.side_effect = RuntimeError("boom")
        handlers.run_hook(payload("Notification", notification_type="permission_prompt", message="m"))

    def test_only_permission_request_returns_output(self):
        """其余事件必须返回 None —— UserPromptSubmit 的 stdout 会进模型上下文。"""
        for ev, kw in (("UserPromptSubmit", {"message": "hi"}),
                       ("Stop", {"last_assistant_message": "x"}),
                       ("Notification", {"notification_type": "permission_prompt", "message": "m"}),
                       ("PermissionDenied", {"tool_name": "Bash", "tool_input": {}})):
            self.assertIsNone(handlers.run_hook(payload(ev, **kw)), ev)


class UserPromptTests(BaseCase):
    def test_records_start_and_first_prompt(self):
        handlers.run_hook(payload("UserPromptSubmit", message="  请修复登录 bug  "))
        st = state.load_state(SID)
        self.assertTrue(st["started_at"])
        self.assertEqual(st["first_prompt"], "请修复登录 bug")
        self.assertEqual(st["cwd"], "/tmp/myproj")

    def test_first_prompt_not_overwritten(self):
        handlers.run_hook(payload("UserPromptSubmit", message="第一条"))
        handlers.run_hook(payload("UserPromptSubmit", message="第二条"))
        self.assertEqual(state.load_state(SID)["first_prompt"], "第一条")

    def test_subagent_ignored(self):
        handlers.run_hook(payload("UserPromptSubmit", message="hi", agent_id="a1"))
        self.assertEqual(state.load_state(SID), {})

    def test_works_before_setup(self):
        config.save_config({"bot_token": "", "chat_id": ""})
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.assertTrue(state.load_state(SID)["started_at"])


class StopTests(BaseCase):
    def test_short_turn_not_sent(self):
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        handlers.run_hook(payload("Stop", last_assistant_message="quick"))
        self.assertEqual(self.tg.sent(), [])

    def test_no_start_record_not_sent(self):
        handlers.run_hook(payload("Stop", last_assistant_message="x"))
        self.assertEqual(self.tg.sent(), [])

    def test_long_turn_sent_with_title_and_duration(self):
        transcript = TMP / "stop.jsonl"
        transcript.write_text(
            json.dumps({"type": "custom-title", "customTitle": "修 bug <b>"}) + "\n", encoding="utf-8")
        handlers.run_hook(payload("UserPromptSubmit", message="请修复登录 bug"))
        self.started_seconds_ago(125)
        handlers.run_hook(payload("Stop", last_assistant_message="已修复 & 测试通过",
                                  transcript_path=str(transcript)))
        sent = self.tg.sent()
        self.assertEqual(len(sent), 1)
        text = sent[0]["text"]
        self.assertEqual(sent[0]["chat_id"], "42")
        self.assertFalse(sent[0]["disable_notification"])
        self.assertIn("任务完成", text)
        self.assertIn("修 bug &lt;b&gt;", text)
        self.assertIn("已修复 &amp; 测试通过", text)
        self.assertIn("2 分 5 秒", text)
        self.assertIn("myproj", text)
        self.assertIn("#sess-123", text)

    def test_second_stop_without_new_prompt_is_silent(self):
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message="a"))
        handlers.run_hook(payload("Stop", last_assistant_message="b"))
        self.assertEqual(len(self.tg.sent()), 1)

    def test_event_off(self):
        cfg = config.load_config()
        cfg["events"]["stop"] = False
        config.save_config(cfg)
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message="x"))
        self.assertEqual(self.tg.sent(), [])

    def test_silent_flag(self):
        cfg = config.load_config()
        cfg["silent"] = {"stop": True}
        config.save_config(cfg)
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message="ok"))
        self.assertTrue(self.tg.sent()[0]["disable_notification"])

    def test_presence_skip(self):
        cfg = config.load_config()
        cfg["skip_if_mac_active_seconds"] = 300
        config.save_config(cfg)
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        with mock.patch.object(config, "mac_idle_seconds", return_value=5.0):
            handlers.run_hook(payload("Stop", last_assistant_message="x"))
        self.assertEqual(self.tg.sent(), [])

    def test_subagent_ignored(self):
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message="x", agent_id="a1"))
        self.assertEqual(self.tg.sent(), [])

    def test_empty_body_still_sends_header(self):
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message=""))
        self.assertIn("任务完成", self.tg.sent()[0]["text"])


class NotificationTests(BaseCase):
    def test_sent_and_rate_limited(self):
        handlers.run_hook(payload("Notification", notification_type="permission_prompt",
                                  message="needs permission to use Bash"))
        handlers.run_hook(payload("Notification", notification_type="permission_prompt",
                                  message="needs permission to use Edit"))
        self.assertEqual(len(self.tg.sent()), 1)
        self.assertIn("需要你批准", self.tg.sent()[0]["text"])
        self.assertIn("use Bash", self.tg.sent()[0]["text"])

    def test_resolved_on_stop(self):
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        handlers.run_hook(payload("Notification", notification_type="permission_prompt", message="m"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message="done"))
        edits = self.tg.edits()
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["message_id"], 101)
        self.assertIn("已处理", edits[0]["text"])
        self.assertNotIn("pending_msgs", state.load_state(SID))

    def test_resolved_even_when_stop_notification_suppressed(self):
        """短轮不发"任务完成"，但旧消息仍要收尾。"""
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        handlers.run_hook(payload("Notification", notification_type="elicitation_dialog", message="?"))
        handlers.run_hook(payload("Stop", last_assistant_message="quick"))
        self.assertEqual(self.tg.sent().__len__(), 1)          # 只有那条提问
        self.assertIn("已处理", self.tg.edits()[0]["text"])

    def test_idle_prompt_off_by_default(self):
        handlers.run_hook(payload("Notification", notification_type="idle_prompt", message="waiting"))
        self.assertEqual(self.tg.sent(), [])

    def test_idle_prompt_not_remembered_as_pending(self):
        cfg = config.load_config()
        cfg["events"]["idle_prompt"] = True
        config.save_config(cfg)
        handlers.run_hook(payload("Notification", notification_type="idle_prompt", message="waiting"))
        self.assertEqual(len(self.tg.sent()), 1)
        self.assertNotIn("pending_msgs", state.load_state(SID))

    def test_unknown_type_ignored(self):
        handlers.run_hook(payload("Notification", notification_type="auth_success", message="ok"))
        self.assertEqual(self.tg.sent(), [])

    def test_falls_back_to_title(self):
        handlers.run_hook(payload("Notification", notification_type="agent_needs_input", title="标题"))
        self.assertIn("标题", self.tg.sent()[0]["text"])


class PermissionDeniedTests(BaseCase):
    def test_off_by_default(self):
        handlers.run_hook(payload("PermissionDenied", tool_name="Bash",
                                  tool_input={"command": "rm -rf /tmp/x"}))
        self.assertEqual(self.tg.sent(), [])

    def test_on(self):
        cfg = config.load_config()
        cfg["events"]["permission_denied"] = True
        config.save_config(cfg)
        handlers.run_hook(payload("PermissionDenied", tool_name="Bash",
                                  tool_input={"command": "rm -rf /tmp/x"}))
        self.assertEqual(len(self.tg.sent()), 1)
        text = self.tg.sent()[0]["text"]
        self.assertIn("自动模式拒绝", text)
        self.assertIn("rm -rf /tmp/x", text)


if __name__ == "__main__":
    unittest.main()
