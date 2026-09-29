"""旧 bot 配置只读沿用，不误写到 Claude 配置目录。"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TMP, config  # noqa: E402


class ConfigMigrationTests(unittest.TestCase):
    def test_legacy_config_is_read_only_fallback(self):
        new = TMP / "migration-new.json"
        old = TMP / "migration-old.json"
        new.unlink(missing_ok=True)
        old.write_text(json.dumps({"bot_token": "old-token", "chat_id": "42",
                                   "events": {"stop": False, "permission_denied": True}}))
        env = {k: v for k, v in os.environ.items() if k != "CODEX_TG_NOTIFY_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(config, "CONFIG_PATH", new), \
             mock.patch.object(config, "LEGACY_CONFIG_PATH", old):
            self.assertEqual(config.effective_config_path(), old)
            cfg = config.load_config()
            self.assertEqual(cfg["bot_token"], "old-token")
            self.assertEqual(cfg["events"], {"stop": False})
            config.save_config(cfg)
            self.assertTrue(new.exists())
            self.assertEqual(json.loads(old.read_text())["bot_token"], "old-token")
            self.assertEqual(new.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
