"""远程批准：按钮、轮询、锁、inbox、决定输出。"""

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SID, USER_ID, BaseCase, approval, config, handlers, payload, state  # noqa: E402


class ApprovalCase(BaseCase):
    def request(self, **kw):
        base = dict(tool_name="Bash", tool_input={"command": "npm test"},
                    permission_suggestions=[{
                        "type": "addRules", "behavior": "allow", "destination": "session",
                        "rules": [{"toolName": "Bash", "ruleContent": "npm test"}]}])
        base.update(kw)
        return payload("PermissionRequest", **base)

    def last_req(self):
        markup = self.tg.sent()[-1]["reply_markup"]["inline_keyboard"]
        return markup[0][0]["callback_data"].split(":")[1]

    def queue_tap(self, choice, user_id=USER_ID, req=None, update_id=7):
        if req is None:
            req = self.last_req()
        self.tg.updates.append({"update_id": update_id, "callback_query": {
            "id": "cq1", "from": {"id": user_id, "username": "saku"},
            "message": {"message_id": self.tg.next_id},
            "data": "%s:%s:%s" % (approval.CALLBACK_PREFIX, req, choice)}})

    def tap_on_first_poll(self, choice, user_id=USER_ID):
        """等到脚本真的去拉更新时才投递点击，模拟"人隔了一会儿才点"。"""
        tg, seen = self.tg, {"n": 0}

        def side_effect(cfg, method, payload=None, timeout=15):
            if method == "getUpdates":
                seen["n"] += 1
                if seen["n"] == 1:
                    self.queue_tap(choice, user_id=user_id)
            return tg(cfg, method, payload, timeout)
        self.tg_mock.side_effect = side_effect

    def short_wait(self):
        cfg = config.load_config()
        cfg["approve"]["wait_seconds"] = 0.05
        config.save_config(cfg)


class DecisionTests(ApprovalCase):
    def test_allow_once(self):
        self.tap_on_first_poll("a")
        out = handlers.run_hook(self.request())
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PermissionRequest")
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})

        sent = self.tg.sent()[0]
        self.assertIn("npm test", sent["text"])
        self.assertEqual(len(sent["reply_markup"]["inline_keyboard"]), 2)
        self.assertIn("已允许", self.tg.edits()[-1]["text"])
        self.assertEqual(self.tg.edits()[-1]["reply_markup"], {"inline_keyboard": []})
        self.assertEqual(self.tg.answers()[0]["text"], "已允许")
        self.assertFalse(config.POLL_LOCK.exists())
        self.assertEqual(approval.read_offset(), 8)

    def test_allow_always_echoes_session_suggestion(self):
        self.tap_on_first_poll("s")
        out = handlers.run_hook(self.request())
        decision = out["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "allow")
        self.assertEqual(decision["updatedPermissions"][0]["destination"], "session")
        self.assertIn("不再询问", self.tg.edits()[-1]["text"])

    def test_allow_always_falls_back_to_first_suggestion(self):
        self.tap_on_first_poll("s")
        out = handlers.run_hook(self.request(permission_suggestions=[
            {"type": "addRules", "behavior": "allow", "destination": "localSettings", "rules": []}]))
        self.assertEqual(out["hookSpecificOutput"]["decision"]["updatedPermissions"][0]["destination"],
                         "localSettings")

    def test_deny(self):
        self.tap_on_first_poll("d")
        out = handlers.run_hook(self.request())
        decision = out["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "deny")
        self.assertIn("message", decision)
        self.assertIn("已拒绝", self.tg.edits()[-1]["text"])

    def test_no_suggestions_means_no_always_button(self):
        self.tap_on_first_poll("a")
        handlers.run_hook(self.request(permission_suggestions=[]))
        self.assertEqual(len(self.tg.sent()[0]["reply_markup"]["inline_keyboard"]), 1)

    def test_always_without_suggestions_degrades_to_allow_once(self):
        self.tap_on_first_poll("s")
        out = handlers.run_hook(self.request(permission_suggestions=[]))
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})


class FallThroughTests(ApprovalCase):
    def test_timeout_hands_back_to_terminal(self):
        self.short_wait()
        self.assertIsNone(handlers.run_hook(self.request()))
        self.assertIn("未响应", self.tg.edits()[-1]["text"])

    def test_mac_active_skips_buttons_entirely(self):
        with mock.patch.object(config, "mac_idle_seconds", return_value=5.0):
            self.assertIsNone(handlers.run_hook(self.request()))
        self.assertEqual(self.tg.sent(), [])

    def test_mac_touched_while_waiting_hands_back(self):
        with mock.patch.object(config, "mac_idle_seconds", return_value=1.0):
            cfg = config.load_config()
            # 触发时算"不在电脑前"，等待中途再检测到触碰：用一次性序列模拟。
            with mock.patch.object(config, "mac_idle_seconds", side_effect=[999.0, 1.0, 1.0]):
                self.assertIsNone(handlers.run_hook(self.request()))
        self.assertIn("检测到你在 Mac 前", self.tg.edits()[-1]["text"])

    def test_disabled(self):
        cfg = config.load_config()
        cfg["approve"]["enabled"] = False
        config.save_config(cfg)
        self.assertIsNone(handlers.run_hook(self.request()))
        self.assertEqual(self.tg.sent(), [])

    def test_subagent_ignored(self):
        self.assertIsNone(handlers.run_hook(self.request(agent_id="a1")))
        self.assertEqual(self.tg.sent(), [])

    def test_group_chat_without_allowed_ids_disables_approval(self):
        cfg = config.load_config()
        cfg["chat_id"] = "-100999"
        config.save_config(cfg)
        self.assertIsNone(handlers.run_hook(self.request()))
        self.assertEqual(self.tg.sent(), [])

    def test_send_failure_falls_through(self):
        self.tg_mock.side_effect = RuntimeError("boom")
        self.assertIsNone(handlers.run_hook(self.request()))

    def test_plain_notification_suppressed_after_button_message(self):
        self.tap_on_first_poll("a")
        handlers.run_hook(self.request())
        handlers.run_hook(payload("Notification", notification_type="permission_prompt", message="需要权限"))
        self.assertEqual(len(self.tg.sent()), 1)


class PollingTests(ApprovalCase):
    def test_foreign_tap_goes_to_its_own_inbox(self):
        """别的会话的点击必须归档到它自己的 inbox，不能被当前等待者吞掉。"""
        self.queue_tap("a", req="deadbeef0000")
        approval.poll_callbacks_once(config.load_config())
        self.assertEqual(approval.read_inbox("deadbeef0000")["choice"], "a")
        self.assertIsNone(approval.read_inbox("deadbeef0000"))

    def test_stranger_tap_rejected(self):
        self.queue_tap("a", user_id=999, req="abc123abc123")
        approval.poll_callbacks_once(config.load_config())
        self.assertIsNone(approval.read_inbox("abc123abc123"))
        self.assertEqual(self.tg.answers()[0]["text"], "无权操作")

    def test_malformed_callback_data_ignored(self):
        for data in ("", "garbage", "x:y:z", "p:onlytwo"):
            self.tg.updates.append({"update_id": 11, "callback_query": {
                "id": "c", "from": {"id": USER_ID}, "data": data}})
        approval.poll_callbacks_once(config.load_config())
        self.assertEqual(self.tg.answers(), [])
        self.assertEqual(list(config.INBOX_DIR.glob("*.json")) if config.INBOX_DIR.exists() else [], [])

    def test_offset_advances_even_for_ignored_updates(self):
        self.tg.updates.append({"update_id": 55, "callback_query": {"id": "c", "data": "garbage"}})
        approval.poll_callbacks_once(config.load_config())
        self.assertEqual(approval.read_offset(), 56)

    def test_poll_failure_does_not_advance_offset(self):
        self.tg_mock.side_effect = RuntimeError("network")
        approval.wait_for_decision(config.load_config(), "req1", time.time() + 0.05, False)
        self.assertIsNone(approval.read_offset())

    def test_sweep_drops_unclaimed_decisions(self):
        approval.write_inbox("old0000", {"choice": "a"})
        approval.write_inbox("new0000", {"choice": "a"})
        old = approval.inbox_path("old0000")
        os.utime(old, (time.time() - 9999, time.time() - 9999))
        approval.sweep_inbox()
        self.assertFalse(old.exists())
        self.assertTrue(approval.inbox_path("new0000").exists())


class LockTests(ApprovalCase):
    def test_lock_is_exclusive_then_released(self):
        self.assertTrue(approval.acquire_poll_lock())
        self.assertFalse(approval.acquire_poll_lock())
        approval.release_poll_lock()
        self.assertTrue(approval.acquire_poll_lock())
        approval.release_poll_lock()

    def test_stale_lock_is_reclaimed(self):
        self.assertTrue(approval.acquire_poll_lock())
        old = time.time() - approval.LOCK_STALE_SECONDS - 5
        os.utime(config.POLL_LOCK, (old, old))
        self.assertTrue(approval.acquire_poll_lock())
        approval.release_poll_lock()

    def test_held_lock_means_no_polling(self):
        """别人在拉更新时，本进程只等自己的 inbox，不去抢 getUpdates。"""
        self.assertTrue(approval.acquire_poll_lock())
        self.addCleanup(approval.release_poll_lock)
        approval.wait_for_decision(config.load_config(), "req1", time.time() + 0.05, False)
        self.assertEqual(self.tg.by("getUpdates"), [])

    def test_decision_from_inbox_needs_no_polling(self):
        approval.write_inbox("req9", {"choice": "a", "from": "someone"})
        found = approval.wait_for_decision(config.load_config(), "req9", time.time() + 5, False)
        self.assertEqual(found["choice"], "a")
        self.assertEqual(self.tg.by("getUpdates"), [])


class StateTests(ApprovalCase):
    def test_perm_handled_until_recorded(self):
        self.tap_on_first_poll("a")
        handlers.run_hook(self.request())
        self.assertGreater(state.load_state(SID)["perm_handled_until"], time.time())


if __name__ == "__main__":
    unittest.main()
