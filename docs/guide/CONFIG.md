# 配置

`~/.config/codex-tg-notify/config.json` 保存 bot token 和选项，权限 600。新文件不存在时，程序只读沿用旧的 `~/.config/claude-tg-notify/config.json`；`setup` 会写入新路径。默认值以 `config.DEFAULT_CONFIG` 为准，完整样例见 [config.example.json](../../config.example.json)。

| 键 | 默认 | 用途 |
|---|---|---|
| `bot_token`、`chat_id` | 空 | Telegram bot 与收消息的聊天；`setup` 配置 |
| `proxy` | 空 | Telegram API 的 HTTP 代理 |
| `min_turn_seconds` | `60` | 短于该时长的任务默认不发完成通知 |
| `away_after_seconds` | `120` | Mac 闲置达到该时长时，短轮也推；0 关闭 |
| `skip_if_mac_active_seconds` | `0` | Mac 近期有键鼠输入时跳过普通通知；0 不跳过 |
| `min_interval_seconds` | `30` | 同类通知的节流间隔 |
| `message_style` | `minimal` | 完成通知的正文：`minimal` 无、`collapsed` 折叠、`full` 展开 |
| `show_activity` | `true` | 完成通知附一行 `PostToolUse` 工具与文件名摘要 |
| `max_text_chars` | `700` | 正文最大长度 |
| `separator`、`gap_lines` | 分隔线、`1` | Telegram 消息外观；空分隔线或 0 行可关闭 |
| `events.stop` | `true` | 是否发送任务完成通知 |
| `silent.stop`、`silent.permission_prompt` | 未设置 | 对应 Telegram 消息静音送达 |
| `allowed_user_ids` | `[]` | 可点批准按钮的用户 id；私聊默认是 chat id，群聊必须显式设置 |
| `approve.enabled` | `true` | 启用远程批准 |
| `approve.wait_seconds` | `90` | 按钮等待时长；改后重新运行 `install` 以同步 hook 超时 |
| `approve.skip_if_mac_active_seconds` | `60` | Mac 活跃时不发按钮，等待时触碰 Mac 则交回 Codex；0 表示每次都发 |

测试和多实例可用环境变量覆盖路径：

| 变量 | 默认 |
|---|---|
| `CODEX_TG_NOTIFY_CONFIG_DIR` | `~/.config/codex-tg-notify` |
| `CODEX_TG_NOTIFY_STATE_DIR` | `~/.cache/codex-tg-notify` |
| `CODEX_HOME` | `~/.codex`，`install` 修改其中的 `hooks.json` |

运行 `./codex-tg-notify status` 查看生效配置路径、安装状态、最近日志。状态命令会遮住 bot token。
