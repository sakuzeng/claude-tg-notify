"""Telegram 文案与转义。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import telegram  # noqa: E402


class FormatTests(unittest.TestCase):
    def test_truncate_and_duration(self):
        self.assertEqual(telegram.truncate("  abc  ", 10), "abc")
        self.assertEqual(len(telegram.truncate("x" * 50, 10)), 10)
        self.assertEqual(telegram.fmt_duration(125), "2 分 5 秒")
        self.assertEqual(telegram.fmt_duration(-5), "0 秒")

    def test_tool_summary_escapes_untrusted_input(self):
        out = telegram.tool_summary("Bash", {"command": "echo '<b>&</b>'"})
        self.assertIn("&lt;b&gt;&amp;&lt;/b&gt;", out)
        self.assertNotIn("<b>&</b>", out)

    def test_session_uses_prompt_not_transcript(self):
        out = telegram.describe_session({"session_id": "abcdefgh1234", "cwd": "/a/b/myproj",
                                         "transcript_path": "/unused"}, {"first_prompt": "修 <bug>"})
        self.assertIn("修 &lt;bug&gt;", out)
        self.assertIn("myproj", out)
        self.assertIn("#abcdefgh", out)

    def test_activity_counts_and_deduplicates(self):
        line = telegram.codex_turn_activity([
            {"name": "apply_patch", "id": "a", "files": ["a&b.py"]},
            {"name": "apply_patch", "id": "a", "files": ["ignored.py"]},
            {"name": "Bash", "id": "b", "files": []},
        ])
        self.assertIn("apply_patch", line)
        self.assertIn("Bash", line)
        self.assertIn("<code>a&amp;b.py</code>", line)
        self.assertNotIn("ignored.py", line)

    def test_activity_caps_display(self):
        line = telegram.codex_turn_activity([
            {"name": "T%d" % i, "id": str(i), "files": ["f%d.py" % i]} for i in range(6)])
        self.assertIn("+2", line)
        self.assertIn("+3", line)

    def test_message_shell(self):
        out = telegram.decorate({"separator": "<b>", "gap_lines": 1}, "正文")
        self.assertTrue(out.startswith("&lt;b&gt;"))
        self.assertTrue(out.endswith(telegram.BLANK_LINE))
        self.assertEqual(telegram.decorate({"separator": "", "gap_lines": 0}, "正文"), "正文")


if __name__ == "__main__":
    unittest.main()
