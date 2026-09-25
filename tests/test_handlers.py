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


class TurnStartTests(BaseCase):
    """起点只记一次 —— 后台任务注入的提示不能把耗时截断（PITFALL 15）。"""

    def test_injected_prompt_does_not_reset_the_clock(self):
        handlers.run_hook(payload("UserPromptSubmit", message="可以"))
        self.started_seconds_ago(232)
        first = state.load_state(SID)["started_at"]
        handlers.run_hook(payload("UserPromptSubmit",
                                  message="<task-notification><task-id>abc</task-id></task-notification>"))
        self.assertEqual(state.load_state(SID)["started_at"], first)

    def test_long_turn_survives_an_injection(self):
        """复现 2026-09-25 的现场：真跑了 232 秒，中途来了条任务通知。"""
        handlers.run_hook(payload("UserPromptSubmit", message="可以"))
        self.started_seconds_ago(232)
        handlers.run_hook(payload("UserPromptSubmit", message="<task-notification/>"))
        handlers.run_hook(payload("Stop", last_assistant_message="所有改动已提交"))
        self.assertEqual(len(self.tg.sent()), 1)
        self.assertIn("3 分 52 秒", self.tg.sent()[0]["text"])

    def test_next_turn_starts_a_new_clock(self):
        handlers.run_hook(payload("UserPromptSubmit", message="第一轮"))
        self.started_seconds_ago(200)
        handlers.run_hook(payload("Stop", last_assistant_message="done"))
        handlers.run_hook(payload("UserPromptSubmit", message="第二轮"))
        handlers.run_hook(payload("Stop", last_assistant_message="quick"))
        self.assertEqual(len(self.tg.sent()), 1)          # 第二轮太短，只发了第一轮

    def test_stale_start_is_discarded(self):
        """上一次 Stop 丢了的话，起点不能一直留着让耗时虚高。"""
        handlers.run_hook(payload("UserPromptSubmit", message="很久以前"))
        self.started_seconds_ago(handlers.STALE_TURN_SECONDS + 60)
        handlers.run_hook(payload("UserPromptSubmit", message="新的一轮"))
        handlers.run_hook(payload("Stop", last_assistant_message="x"))
        self.assertEqual(self.tg.sent(), [])              # 重新计时 → 这轮太短 → 不发

    def test_broken_start_value_recovers(self):
        st = state.load_state(SID)
        st["started_at"] = "坏值"
        state.save_state(SID, st)
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.assertIsInstance(state.load_state(SID)["started_at"], float)


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
        self.assertIn("2 分 5 秒", text)
        self.assertIn("myproj", text)
        self.assertIn("#sess-123", text)
        # 默认 minimal：只报哪个做完了，不搬正文。
        self.assertNotIn("已修复 &amp; 测试通过", text)


class AwayTests(BaseCase):
    """人不在 Mac 前时，短轮也要推 —— 阈值只用来挡"你就坐在电脑前"的刷屏。"""

    def short_turn(self, idle, **cfg_over):
        cfg = config.load_config()
        cfg["min_turn_seconds"] = 60          # BaseCase 默认 30，这组用例要的是 54 < 60
        cfg.update(cfg_over)
        config.save_config(cfg)
        handlers.run_hook(payload("UserPromptSubmit", message="接下来怎么做呢"))
        self.started_seconds_ago(54)
        with mock.patch.object(config, "mac_idle_seconds", return_value=idle):
            handlers.run_hook(payload("Stop", last_assistant_message="整体做法和网上主流一致"))
        return self.tg.sent()

    def test_short_turn_sent_when_away(self):
        """2026-09-25 的现场：54 秒的回答，人在手机上。"""
        sent = self.short_turn(idle=600.0, away_after_seconds=120)
        self.assertEqual(len(sent), 1)
        self.assertIn("54 秒", sent[0]["text"])

    def test_short_turn_still_skipped_when_at_the_mac(self):
        self.assertEqual(self.short_turn(idle=5.0, away_after_seconds=120), [])

    def test_feature_off_by_zero(self):
        self.assertEqual(self.short_turn(idle=600.0, away_after_seconds=0), [])

    def test_unknown_idle_keeps_the_threshold(self):
        """非 macOS 探测不到空闲时间，必须沿用阈值，不能突然开始刷屏。"""
        self.assertEqual(self.short_turn(idle=None, away_after_seconds=120), [])

    def test_away_does_not_override_the_event_switch(self):
        cfg = config.load_config()
        cfg["events"]["stop"] = False
        config.save_config(cfg)
        self.assertEqual(self.short_turn(idle=600.0, away_after_seconds=120), [])


class StopStyleTests(BaseCase):
    """message_style 三档 + 做了什么那一行。"""

    def stop_text(self, transcript=None, **cfg_over):
        if cfg_over:
            cfg = config.load_config()
            cfg.update(cfg_over)
            config.save_config(cfg)
        handlers.run_hook(payload("UserPromptSubmit", message="hi"))
        self.started_seconds_ago(60)
        handlers.run_hook(payload("Stop", last_assistant_message="正文 <b>在此</b>",
                                  transcript_path=transcript))
        return self.tg.sent()[0]["text"]

    def test_minimal_is_the_default(self):
        text = self.stop_text()
        self.assertNotIn("正文", text)
        self.assertLessEqual(len(text.strip().splitlines()), 6)

    def test_full_carries_the_body(self):
        text = self.stop_text(message_style="full")
        self.assertIn("正文 &lt;b&gt;在此&lt;/b&gt;", text)
        self.assertNotIn("blockquote", text)

    def test_collapsed_wraps_body_in_expandable_quote(self):
        text = self.stop_text(message_style="collapsed")
        self.assertIn("<blockquote expandable>", text)
        self.assertIn("正文 &lt;b&gt;在此&lt;/b&gt;", text)

    def test_unknown_style_behaves_like_full(self):
        self.assertIn("正文 &lt;b&gt;在此&lt;/b&gt;", self.stop_text(message_style="没听说过"))

    def test_activity_line_added_from_transcript(self):
        path = TMP / "stop-activity.jsonl"
        path.write_text(json.dumps({
            "type": "assistant", "timestamp": "2099-01-01T00:00:00.000Z",
            "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/x.py"}},
                                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]},
        }) + "\n", encoding="utf-8")
        text = self.stop_text(transcript=str(path))
        self.assertIn("🛠", text)
        self.assertIn("x.py", text)

    def test_activity_can_be_turned_off(self):
        path = TMP / "stop-activity.jsonl"
        self.assertNotIn("🛠", self.stop_text(transcript=str(path), show_activity=False))

    def test_message_shell_is_applied(self):
        text = self.stop_text()
        self.assertTrue(text.startswith("━"), text[:20])
        self.assertTrue(text.endswith(telegram.BLANK_LINE), repr(text[-5:]))

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
