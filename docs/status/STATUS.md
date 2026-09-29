# 当前状态

**2026-09-29，版本 1.0.0。** Claude 版已改为 Codex hooks 版。`UserPromptSubmit`、`PostToolUse`、`Stop` 和 `PermissionRequest` 的输入、输出与安装结构已按 [Codex 官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks) 调整。

| 验证项 | 状态 |
|---|---|
| 离线单元与子进程测试 | 已通过；运行 `python3 -m unittest discover -s tests -q` 重验 |
| 旧 bot 配置只读沿用、新配置写入 | 离线测试通过；本机已从旧配置读取并发送测试消息，未改动旧文件 |
| 合并 Codex `hooks.json` 且保留其他 hook | 离线隔离安装通过；本机已安装四条，旧入口已清理，备份已生成 |
| Telegram Bot API 通道 | 本机 `test` 已发送成功一条标记的验收测试消息 |
| 本机 Codex 任务完成通知 | 未实测真实 Codex hook |
| Telegram 按钮点击与 Codex 接受决定 | 假 Bot API 测试通过，尚未真机验证 |

按钮点击和真实 Codex hook 仍需验收；安装状态不等于 Codex 已信任该 hook。见 [README 验收命令](../../README.md)。
