# 架构与数据流

Codex 从 `~/.codex/hooks.json` 运行 `python3 <仓库>/codex-tg-notify hook`，通过 stdin 传入事件 JSON。入口只调用包内的 `cli.main`。包的 Python 名称暂保留 `claude_tg_notify`，以兼容旧安装。

```text
UserPromptSubmit ─► sessions/<session_id>.json：turn_id、started_at、first_prompt
PostToolUse      ─► activity/<session_id>-<turn_id>.jsonl：工具名、调用 id、文件名
Stop             ─► 读取状态和活动，按时长与 Mac 空闲规则决定 sendMessage
PermissionRequest ► sendMessage(两按钮) ► 等待 Telegram callback ► 输出 allow/deny JSON
```

四个事件的输入输出契约见 [HOOKS.md](HOOKS.md)。`Stop` 在后台运行；批准请求同步等待，超时、网络失败或 Mac 重新活跃时不输出决定，由 Codex 展示自己的批准界面。hook 捕获异常、记录日志、退出 0。

| 模块 | 职责 |
|---|---|
| `config` | 路径、配置、日志、Mac 空闲探测 |
| `state` | 每轮状态、工具活动、节流与空闲策略 |
| `telegram` | Bot API 与 HTML 消息文案，转义来自 Codex 的文本 |
| `approval` | 按钮、回调鉴权、轮询锁、inbox、决定输出 |
| `handlers` | Codex 事件分发 |
| `install` | 备份并合并 Codex hooks；识别本项目旧条目 |
| `cli` | `setup`、`install`、`status`、`test`、`hook` 命令 |

配置保存在 `~/.config/codex-tg-notify/config.json`，状态和日志在 `~/.cache/codex-tg-notify/`。`sessions/` 中只保存首条提示、项目、轮次和时间；`activity/` 只保存工具名、调用 id 和文件名，不保存命令或工具结果。`PostToolUse` 使用追加写入；`Stop` 读取后删除本轮活动文件。Codex transcript 格式不稳定，本项目不依赖它。

Telegram `getUpdates` 只能有一个消费者。并发批准请求用 `poll.lock` 互斥；拉到的 callback 按随机请求 id 写入 `inbox/<req>.json`，由各自等待的 hook 认领。只有 `allowed_user_ids` 中的用户点击才会写入决定；私聊默认允许 chat id 对应的用户，群聊需要显式白名单。消息在决定、超时或回到 Mac 前后被改写并移除按钮。

任务完成消息默认只含首条提示、项目、耗时和一行工具摘要。`message_style=collapsed/full` 可以附上 Codex `Stop.last_assistant_message`。所有外部文本都经 HTML 转义后发送；Telegram bot token 只留在本机配置中。
