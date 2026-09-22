"""claude-tg-notify: 把 Claude Code 的会话事件推到 Telegram，并可在 Telegram 上批准工具调用。

只在这里定义包级常量，不导入任何子模块 —— 打包时 setuptools 要靠 import 本文件读 VERSION，
保持它零依赖、零副作用，版本号就永远读得到。
"""

APP = "claude-tg-notify"
VERSION = "0.3.1"

__all__ = ["APP", "VERSION"]
