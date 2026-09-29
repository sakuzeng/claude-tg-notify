# codex-tg-notify

把本机 Codex 的任务完成与批准请求推到 Telegram。批准消息带 **允许一次 / 拒绝** 按钮，点击后决定交回 Codex。只用 Python 标准库；clone 后无需安装 Python 包。

## 功能

| Codex 事件 | Telegram 消息 |
|---|---|
| `Stop` | ✅ 任务完成：首条提示、项目、耗时、工具与修改过的文件；默认超过 60 秒才推，Mac 闲置超过 120 秒时短轮也推 |
| `PermissionRequest` | 🔔 需要批准：工具名称和输入摘要，带允许一次 / 拒绝按钮；超时后交回 Codex 正常批准界面 |

`UserPromptSubmit` 记录起点和首条提示；`PostToolUse` 记录工具名称及文件名。工具活动不解析 Codex transcript，也不调用模型。项目不读取或上传完整对话记录。Telegram 消息可能包含你给 Codex 的首条提示、批准请求中的命令及文件名；请使用你信任的 bot 和私聊。

Codex 目前没有本项目原先使用的 Claude `Notification` 与 `PermissionDenied` hook，因此“需要回答”“空闲提醒”和“自动模式拒绝”消息暂不提供。Codex 的 `PermissionRequest` 也不支持“始终允许”的 `updatedPermissions`，按钮只批准当前一次。[Codex Hooks 文档](https://learn.chatgpt.com/docs/hooks)

## 快速开始

在本仓库目录执行：

```bash
./codex-tg-notify setup      # 配置 Telegram bot；成功时会发送一条连接测试消息
./codex-tg-notify install    # 备份并合并到 ~/.codex/hooks.json，保留其他 hook
./codex-tg-notify status     # 检查 hook 是否写入、配置与最近日志；不代表已获信任
```

首次启用或修改 hook 后，在 **Codex CLI** 中执行 `/hooks`，逐条审查并信任本项目的 `UserPromptSubmit`、`PostToolUse`、`Stop` 命令；已有会话建议重启。暂不使用远程批准时，可让 `PermissionRequest` 保持未信任。若列表还有其他来源的 hook，不要直接选择“全部信任”。Codex 会跳过尚未信任的 hook。[官方信任说明](https://learn.chatgpt.com/docs/hooks)

已在旧版 `~/.config/claude-tg-notify/config.json` 配好 bot 的用户，新版在没有新配置时会只读沿用它。重新执行 `setup` 后，配置写入 `~/.config/codex-tg-notify/config.json`。不会修改 Claude 的 `~/.claude/settings.json`。

验收命令：

```bash
python3 -m unittest discover -s tests -q   # 离线测试，不发 Telegram
./codex-tg-notify install --print           # 预览安装内容，不写配置
./codex-tg-notify test                      # 真正发一条 Telegram 消息
./codex-tg-notify test --approve            # 真正发按钮消息，手机点后终端显示 hook 决定
```

最后两条会响你的手机；需要已配置 bot、代理或网络可达。`test --approve` 验证 Bot API 和按钮路径；Codex 实际接受决定还需在真实的 `PermissionRequest` 中验证。

## 配置与限制

配置文件：`~/.config/codex-tg-notify/config.json`，状态与日志：`~/.cache/codex-tg-notify/`。默认值和字段见 [配置说明](docs/guide/CONFIG.md)。

- `approve.skip_if_mac_active_seconds` 默认 60：Mac 近期有键鼠输入时交回 Codex 本地批准，不在 Telegram 发按钮。若想每次都在手机上批准，设为 `0`。
- 群聊必须设置 `allowed_user_ids`，否则远程批准关闭；私聊默认只允许 chat id 对应的用户点按钮。
- `approve.wait_seconds` 改大后需要重新运行 `install`，让 Codex hook 超时同步增加。
- 一个 bot 只服务一台机器；Telegram `getUpdates` 只有一个消费者。手机须能连接 Telegram。
- Mac 空闲检测依赖 `ioreg`；其他平台沿用任务时长阈值。
- 新版包的 Python 导入名仍为 `claude_tg_notify`，用于兼容旧安装；面向用户的命令、配置与 Codex hook 已改为 `codex-tg-notify`。

排障见 [排查速查表](docs/ops/TROUBLESHOOTING.md)，代码结构与事件契约见 [架构](docs/guide/ARCHITECTURE.md)和 [Codex Hooks](docs/guide/HOOKS.md)。

## License

MIT，见 [LICENSE](LICENSE)。
