"""文本构造：截断、时长、工具简述、会话描述。"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import TMP, telegram  # noqa: E402


class TruncateTests(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(telegram.truncate("  abc  ", 10), "abc")

    def test_long_text_gets_ellipsis_and_fits(self):
        out = telegram.truncate("x" * 50, 10)
        self.assertEqual(len(out), 10)
        self.assertTrue(out.endswith("…"))

    def test_limit_zero(self):
        self.assertEqual(telegram.truncate("abc", 0), "…")


class DurationTests(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(telegram.fmt_duration(41), "41 秒")

    def test_minutes(self):
        self.assertEqual(telegram.fmt_duration(125), "2 分 5 秒")

    def test_hours(self):
        self.assertEqual(telegram.fmt_duration(3 * 3600 + 4 * 60 + 9), "3 小时 4 分")

    def test_negative_clamped(self):
        self.assertEqual(telegram.fmt_duration(-5), "0 秒")


class ToolSummaryTests(unittest.TestCase):
    def test_bash_shows_command(self):
        out = telegram.tool_summary("Bash", {"command": "npm test"})
        self.assertIn("<b>Bash</b>", out)
        self.assertIn("<pre>npm test</pre>", out)

    def test_file_tools_show_path(self):
        self.assertIn("/tmp/a.py", telegram.tool_summary("Edit", {"file_path": "/tmp/a.py"}))
        self.assertIn("/tmp/n.ipynb", telegram.tool_summary("NotebookEdit", {"notebook_path": "/tmp/n.ipynb"}))

    def test_web_tools_show_url_or_query(self):
        self.assertIn("example.com", telegram.tool_summary("WebFetch", {"url": "https://example.com"}))
        self.assertIn("天气", telegram.tool_summary("WebSearch", {"query": "天气"}))

    def test_unknown_tool_dumps_json(self):
        out = telegram.tool_summary("Weird", {"a": 1})
        self.assertIn("Weird", out)
        self.assertIn("a", out)

    def test_html_is_escaped(self):
        out = telegram.tool_summary("Bash", {"command": "echo '<b>&</b>'"})
        self.assertIn("&lt;b&gt;&amp;&lt;/b&gt;", out)

    def test_no_body_means_name_only(self):
        self.assertEqual(telegram.tool_summary("Glob", {}), "<b>Glob</b>")

    def test_non_dict_input_survives(self):
        self.assertIn("Weird", telegram.tool_summary("Weird", "not a dict"))

    def test_long_command_truncated(self):
        out = telegram.tool_summary("Bash", {"command": "y" * 900})
        self.assertLess(len(out), 500)


class SessionTitleTests(unittest.TestCase):
    def test_missing_path_is_none(self):
        self.assertIsNone(telegram.session_title(None))
        self.assertIsNone(telegram.session_title(str(TMP / "nope.jsonl")))

    def test_last_custom_title_wins(self):
        p = TMP / "title.jsonl"
        p.write_text(
            json.dumps({"type": "user", "message": "x"}) + "\n"
            + json.dumps({"type": "custom-title", "customTitle": "旧"}) + "\n"
            + "{ broken json\n"
            + json.dumps({"type": "custom-title", "customTitle": "新"}) + "\n",
            encoding="utf-8")
        self.assertEqual(telegram.session_title(str(p)), "新")

    def test_no_title_record(self):
        p = TMP / "notitle.jsonl"
        p.write_text(json.dumps({"type": "user"}) + "\n", encoding="utf-8")
        self.assertIsNone(telegram.session_title(str(p)))


class DescribeSessionTests(unittest.TestCase):
    def test_falls_back_to_first_prompt(self):
        out = telegram.describe_session({"session_id": "abcdefgh1234", "cwd": "/a/b/myproj"},
                                        {"first_prompt": "修 <bug>"})
        self.assertIn("修 &lt;bug&gt;", out)
        self.assertIn("myproj", out)
        self.assertIn("#abcdefgh", out)

    def test_unnamed_when_nothing_known(self):
        self.assertIn("(未命名)", telegram.describe_session({"session_id": "x", "cwd": "/tmp/p"}, {}))

    def test_title_beats_first_prompt(self):
        p = TMP / "d.jsonl"
        p.write_text(json.dumps({"type": "custom-title", "customTitle": "标题"}) + "\n", encoding="utf-8")
        out = telegram.describe_session({"session_id": "x", "cwd": "/tmp/p", "transcript_path": str(p)},
                                        {"first_prompt": "提示"})
        self.assertIn("标题", out)
        self.assertNotIn("提示", out)


if __name__ == "__main__":
    unittest.main()
