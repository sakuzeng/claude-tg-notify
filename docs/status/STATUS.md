# 当前状态

**2026-09-29，版本 1.0.1。** Claude 版已改为 Codex hooks 版。`UserPromptSubmit`、`PostToolUse`、`Stop` 和 `PermissionRequest` 的输入、输出与安装结构已按 [Codex 官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks) 调整。

| 验证项 | 状态 |
|---|---|
| 离线单元与子进程测试 | 80 项通过；包含 700 字折叠正文、两次 Bash 和一次 apply_patch 的组合测试；运行 `python3 -m unittest discover -s tests -q` 重验 |
| 旧 bot 配置只读沿用、新配置写入 | 离线测试通过；本机已从旧配置读取并发送测试消息，未改动旧文件 |
| 合并 Codex `hooks.json` 且保留其他 hook | 离线隔离安装通过；本机已写入四条，旧入口已清理，备份已生成；Codex CLI `/hooks` 现显示所有来源共 9 条已启用，包括本项目四条 |
| Telegram Bot API 通道 | 本机 `test`、模拟 `Stop`、真实 Codex CLI 的同步 `Stop` 均已发送成功；模拟消息验证了 1299 字正文和三次工具调用 |
| 本机 Codex 任务完成通知 | 新建的真实 CLI 工具任务已触发 `UserPromptSubmit`、`PostToolUse` 和同步 `Stop`，并发出 Telegram 通知；验收使用临时配置将阈值设为 1 秒，正式配置仍为 60 秒 |
| Telegram 按钮点击与 Codex 接受决定 | `PermissionRequest` hook 当前已启用；假 Bot API 测试通过，按当前安排暂不做真机验收 |

真实 Codex hook 的完成通知已确认发送。远程批准的真机验收暂缓。`PermissionRequest` 目前处于启用状态，若需完全停用远程批准，应单独禁用本项目该 hook 或关闭 `approve.enabled`。见 [README 验收命令](../../README.md)。
