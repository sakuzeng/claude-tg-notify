"""settings.json 合并、hook 命令构造、以及升级时对旧条目的识别。"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TMP, BaseCase, config, handlers, install  # noqa: E402

OTHER_HOOK = {"hooks": [{"type": "command", "command": "echo other"}]}


class SettingsCase(BaseCase):
    def settings_file(self, initial=None):
        path = TMP / "claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(initial if initial is not None else {}), encoding="utf-8")
        return path


class InstallTests(SettingsCase):
    def test_merges_and_is_idempotent(self):
        path = self.settings_file({"model": "opus", "hooks": {"Stop": [dict(OTHER_HOOK)]}})
        install.install_hooks(path)
        install.install_hooks(path)
        data = json.loads(path.read_text())

        self.assertEqual(data["model"], "opus")
        stop = data["hooks"]["Stop"]
        self.assertEqual(len(stop), 2)
        self.assertEqual(stop[0]["hooks"][0]["command"], "echo other")
        self.assertTrue(stop[1]["hooks"][0]["async"])
        self.assertEqual(data["hooks"]["Notification"][0]["matcher"], handlers.NOTIFICATION_MATCHER)
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        self.assertTrue(all(install.hooks_installed(path).values()))

    def test_permission_request_is_synchronous_with_room_to_wait(self):
        path = self.settings_file()
        install.install_hooks(path)
        entry = json.loads(path.read_text())["hooks"]["PermissionRequest"][0]["hooks"][0]
        self.assertNotIn("async", entry)
        self.assertGreaterEqual(entry["timeout"], int(config.load_config()["approve"]["wait_seconds"]) + 30)

    def test_backup_written(self):
        path = self.settings_file({"model": "opus"})
        backup = install.install_hooks(path)
        self.assertIsNotNone(backup)
        self.assertEqual(json.loads(backup.read_text())["model"], "opus")

    def test_creates_file_when_absent(self):
        path = TMP / "claude-fresh" / "settings.json"
        self.assertIsNone(install.install_hooks(path))
        self.assertTrue(all(install.hooks_installed(path).values()))

    def test_uninstall_restores_other_hooks(self):
        path = self.settings_file({"hooks": {"Stop": [dict(OTHER_HOOK)]}})
        install.install_hooks(path)
        install.uninstall_hooks(path)
        data = json.loads(path.read_text())
        self.assertEqual(data["hooks"], {"Stop": [OTHER_HOOK]})
        self.assertFalse(any(install.hooks_installed(path).values()))

    def test_uninstall_drops_hooks_key_when_empty(self):
        path = self.settings_file({"model": "opus"})
        install.install_hooks(path)
        install.uninstall_hooks(path)
        data = json.loads(path.read_text())
        self.assertNotIn("hooks", data)
        self.assertEqual(data["model"], "opus")

    def test_uninstall_on_clean_file_is_noop(self):
        path = self.settings_file({"hooks": {"Stop": [dict(OTHER_HOOK)]}})
        self.assertIsNone(install.uninstall_hooks(path))


class MigrationTests(SettingsCase):
    """0.2.0 的单文件入口升级到 0.3.0 的包入口时，旧条目必须被认出并替换。"""

    LEGACY = {"hooks": [{"type": "command",
                         "command": "python3 '/old/path/claude_tg_notify.py' hook", "timeout": 30}]}

    def test_legacy_single_file_entry_is_recognized(self):
        self.assertTrue(install.is_ours(self.LEGACY))

    def test_module_entry_is_recognized(self):
        self.assertTrue(install.is_ours({"hooks": [{"command": "'/v/bin/python3' -m claude_tg_notify hook"}]}))

    def test_console_script_entry_is_recognized(self):
        self.assertTrue(install.is_ours({"hooks": [{"command": "claude-tg-notify hook"}]}))

    def test_unrelated_entry_is_not_ours(self):
        self.assertFalse(install.is_ours(OTHER_HOOK))
        self.assertFalse(install.is_ours({"hooks": [{"command": "python3 /other/project/hook.py"}]}))
        self.assertFalse(install.is_ours({"hooks": []}))

    def test_upgrade_replaces_instead_of_duplicating(self):
        path = self.settings_file({"hooks": {"Stop": [dict(self.LEGACY)], "Notification": [dict(self.LEGACY)]}})
        install.install_hooks(path)
        data = json.loads(path.read_text())
        self.assertEqual(len(data["hooks"]["Stop"]), 1)
        self.assertEqual(len(data["hooks"]["Notification"]), 1)
        self.assertNotIn("/old/path", json.dumps(data))

    def test_uninstall_removes_legacy_entries(self):
        path = self.settings_file({"hooks": {"Stop": [dict(self.LEGACY)]}})
        install.uninstall_hooks(path)
        self.assertNotIn("hooks", json.loads(path.read_text()))


class HookCommandTests(BaseCase):
    def test_prefers_repo_shim(self):
        cmd = install.hook_command()
        self.assertTrue(config.SHIM_PATH.exists(), "仓库根目录应有 claude-tg-notify 垫片")
        self.assertIn(str(config.SHIM_PATH), cmd)
        self.assertTrue(cmd.endswith(" hook"))

    def test_falls_back_to_module_entry_when_shim_missing(self):
        missing = Path("/nonexistent/claude-tg-notify")
        with mock.patch.object(config, "SHIM_PATH", missing):
            cmd = install.hook_command()
        self.assertIn("-m claude_tg_notify hook", cmd)
        self.assertIn(sys.executable.split("/")[-1], cmd)

    def test_command_is_recognized_as_ours(self):
        self.assertTrue(install.is_ours({"hooks": [{"command": install.hook_command()}]}))


class StaleTimeoutTests(SettingsCase):
    def test_no_warning_when_consistent(self):
        path = self.settings_file()
        install.install_hooks(path)
        self.assertIsNone(install.stale_timeout_warning(config.load_config(), path))

    def test_warns_when_wait_raised_without_reinstall(self):
        path = self.settings_file()
        install.install_hooks(path)
        cfg = config.load_config()
        cfg["approve"]["wait_seconds"] = 600
        config.save_config(cfg)
        warning = install.stale_timeout_warning(config.load_config(), path)
        self.assertIsNotNone(warning)
        self.assertIn("install", warning)

    def test_no_warning_when_not_installed(self):
        self.assertIsNone(install.stale_timeout_warning(config.load_config(), self.settings_file()))


if __name__ == "__main__":
    unittest.main()
