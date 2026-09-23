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


class TurnActivityTests(unittest.TestCase):
    """本轮做了什么：纯读 transcript 的 tool_use 记录，不经过模型。"""

    def write(self, name, records):
        path = TMP / name
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        return str(path)

    def tool_use(self, stamp, *tools):
        content = [{"type": "tool_use", "name": n, "input": inp} for n, inp in tools]
        return {"type": "assistant", "timestamp": stamp, "message": {"content": content}}

    def test_missing_path_or_no_tools(self):
        self.assertEqual(telegram.turn_activity(None, 0), "")
        self.assertEqual(telegram.turn_activity("/nope/none.jsonl", 0), "")
        path = self.write("act-empty.jsonl", [{"type": "user", "timestamp": "2026-01-01T00:00:00.000Z"}])
        self.assertEqual(telegram.turn_activity(path, 0), "")

    def test_counts_and_files(self):
        path = self.write("act-basic.jsonl", [
            self.tool_use("2026-01-01T00:00:10.000Z",
                          ("Edit", {"file_path": "/a/handlers.py"}),
                          ("Edit", {"file_path": "/a/telegram.py"}),
                          ("Bash", {"command": "ls"})),
            self.tool_use("2026-01-01T00:00:20.000Z", ("Edit", {"file_path": "/a/handlers.py"})),
        ])
        line = telegram.turn_activity(path, 0)
        self.assertTrue(line.startswith("🛠 "), line)
        self.assertIn("Edit×3", line)
        self.assertIn("Bash", line)          # 只出现一次就不带 ×N
        self.assertNotIn("Bash×", line)
        self.assertIn("handlers.py", line)   # 同名文件只列一次
        self.assertEqual(line.count("handlers.py"), 1)
        self.assertIn("telegram.py", line)

    def test_only_counts_this_turn(self):
        path = self.write("act-since.jsonl", [
            self.tool_use("2026-01-01T00:00:00.000Z", ("Read", {"file_path": "/a/old.py"})),
            self.tool_use("2026-01-01T01:00:00.000Z", ("Write", {"file_path": "/a/new.py"})),
        ])
        since = telegram._parse_ts("2026-01-01T00:30:00.000Z")
        line = telegram.turn_activity(path, since)
        self.assertIn("Write", line)
        self.assertNotIn("Read", line)
        self.assertIn("new.py", line)

    def test_caps_tools_and_files(self):
        path = self.write("act-cap.jsonl", [self.tool_use(
            "2026-01-01T00:00:10.000Z",
            *[("T%d" % i, {}) for i in range(6)],
            *[("Edit", {"file_path": "/a/f%d.py" % i}) for i in range(5)])])
        line = telegram.turn_activity(path, 0)
        self.assertIn("+3", line)   # 7 种工具里只显示 4 种
        self.assertIn("+2", line)   # 5 个文件里只显示 3 个

    def test_broken_lines_survive(self):
        path = TMP / "act-broken.jsonl"
        path.write_text('{"tool_use" 坏行\n' + json.dumps(
            self.tool_use("2026-01-01T00:00:10.000Z", ("Bash", {"command": "ls"}))) + "\n", encoding="utf-8")
        self.assertIn("Bash", telegram.turn_activity(str(path), 0))

    def test_record_without_timestamp_is_ignored(self):
        path = self.write("act-nots.jsonl", [
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}])
        self.assertEqual(telegram.turn_activity(path, 0), "")

    def test_html_escaped(self):
        path = self.write("act-escape.jsonl", [
            self.tool_use("2026-01-01T00:00:10.000Z", ("Write", {"file_path": "/a/a&b.py"}))])
        self.assertIn("a&amp;b.py", telegram.turn_activity(path, 0))


class DecorateTests(unittest.TestCase):
    """分隔线与尾部空行：浅色主题下把相邻消息隔开。"""

    def test_default_shell(self):
        out = telegram.decorate({"separator": "━━━", "gap_lines": 1}, "正文")
        self.assertEqual(out, "━━━\n正文\n" + telegram.BLANK_LINE)

    def test_both_off(self):
        self.assertEqual(telegram.decorate({"separator": "", "gap_lines": 0}, "正文"), "正文")

    def test_missing_keys_mean_off(self):
        self.assertEqual(telegram.decorate({}, "正文"), "正文")

    def test_gap_is_capped_and_tolerant(self):
        self.assertEqual(telegram.decorate({"gap_lines": 99}, "x").count(telegram.BLANK_LINE), 5)
        self.assertEqual(telegram.decorate({"gap_lines": "坏值"}, "x"), "x")

    def test_separator_is_escaped(self):
        self.assertTrue(telegram.decorate({"separator": "<b>"}, "x").startswith("&lt;b&gt;"))
