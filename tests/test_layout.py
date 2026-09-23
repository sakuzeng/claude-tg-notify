"""对包结构本身的静态约束。

拆成多模块之后有两条规矩必须机器来守，靠人记会忘：
1. 零第三方依赖 —— hook 跑在裸子 shell 里，多一个依赖就多一种装不上的可能。
2. 跨模块调用一律走模块对象（`telegram.send_message(...)`）而不是 `from .telegram import send_message`。
   后者在导入时就把名字绑死了，测试再打 `telegram.tg_api` 就打不中，桩会静默失效。
3. 除 cli 外不许 print —— UserPromptSubmit 的 stdout 会被当成上下文塞给模型。
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ROOT  # noqa: E402

PKG = ROOT / "claude_tg_notify"

#: 允许出现的绝对导入，全部是标准库。新增依赖必须先改这里，等于一道人工闸门。
ALLOWED_ABSOLUTE = {
    "argparse", "ast", "datetime", "html", "json", "os", "pathlib", "re",
    "subprocess", "sys", "time", "typing", "urllib", "uuid",
}

#: 可以从包根 `from . import X` 拿到的名字：子模块，加 __init__ 里的两个常量。
SUBMODULES = {"approval", "cli", "config", "handlers", "install", "state", "telegram"}
PKG_CONSTANTS = {"APP", "VERSION"}

#: 只有它是命令行门面，允许 print；也只有它作为入口可以 `from .cli import main`。
CLI_MODULES = {"cli.py", "__main__.py"}


def modules():
    return sorted(PKG.glob("*.py"))


def tree_of(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class DependencyTests(unittest.TestCase):
    def test_only_stdlib_is_imported(self):
        for path in modules():
            for node in ast.walk(tree_of(path)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        self.assertIn(root, ALLOWED_ABSOLUTE, "%s 引入了非标准库 %s" % (path.name, alias.name))
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    root = (node.module or "").split(".")[0]
                    self.assertIn(root, ALLOWED_ABSOLUTE, "%s 引入了非标准库 %s" % (path.name, node.module))

    def test_package_init_has_no_side_effects(self):
        """打包时 setuptools 要 import __init__ 读 VERSION，它必须零导入零副作用。"""
        tree = tree_of(PKG / "__init__.py")
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [])


class CallConventionTests(unittest.TestCase):
    def test_cross_module_imports_bind_modules_not_names(self):
        for path in modules():
            if path.name in CLI_MODULES:
                continue
            for node in ast.walk(tree_of(path)):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                self.assertIsNone(
                    node.module,
                    "%s 用了 `from .%s import ...`；请改成 `from . import %s` 并通过模块名调用，"
                    "否则测试打桩会失效" % (path.name, node.module, node.module))
                for alias in node.names:
                    self.assertIn(alias.name, SUBMODULES | PKG_CONSTANTS,
                                  "%s 从包根导入了意料之外的 %s" % (path.name, alias.name))

    def test_main_module_only_pulls_the_entry_point(self):
        tree = tree_of(PKG / "__main__.py")
        froms = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
        self.assertEqual([(n.module, [a.name for a in n.names]) for n in froms], [("cli", ["main"])])


class StdoutTests(unittest.TestCase):
    def test_no_print_outside_cli(self):
        for path in modules():
            if path.name in CLI_MODULES:
                continue
            for node in ast.walk(tree_of(path)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                    self.fail("%s:%d 里有 print；hook 的 stdout 会被 Claude Code 当作数据"
                              % (path.name, node.lineno))

    def test_no_stdout_writes_outside_cli(self):
        for path in modules():
            if path.name in CLI_MODULES:
                continue
            src = path.read_text(encoding="utf-8")
            self.assertNotIn("sys.stdout", src, "%s 直接写了 stdout" % path.name)


class ShapeTests(unittest.TestCase):
    def test_every_module_is_documented(self):
        for path in modules():
            self.assertTrue(ast.get_docstring(tree_of(path)), "%s 缺模块 docstring" % path.name)

    def test_modules_stay_small(self):
        """拆分的意义就在这；超了说明该再切一刀，而不是继续堆。"""
        for path in modules():
            lines = len(path.read_text(encoding="utf-8").splitlines())
            self.assertLess(lines, 330, "%s 有 %d 行，考虑再拆" % (path.name, lines))

    def test_expected_modules_exist(self):
        self.assertEqual({p.stem for p in modules()} - {"__init__", "__main__"}, SUBMODULES)


if __name__ == "__main__":
    unittest.main()
