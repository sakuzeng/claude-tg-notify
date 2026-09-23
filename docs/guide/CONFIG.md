# 配置项

> 常青规范。文件：`~/.config/claude-tg-notify/config.json`，权限 600。
> 默认值的唯一事实源是代码里的 `DEFAULT_CONFIG`；缺的键取默认，`events` / `approve` / `silent` 三个子表按键合并。
> 完整样例：[`../../config.example.json`](../../config.example.json)。

| 键 | 默认 | 说明 |
|---|---|---|
| `bot_token` | `""` | @BotFather 给的 token，`setup` 写入 |
| `chat_id` | `""` | 收消息的聊天；`setup` 从你发给 bot 的第一条消息自动取 |
| `proxy` | `""` | HTTP 代理，如 `http://127.0.0.1:7890`；留空直连。Clash TUN 模式不需要 |
| `min_turn_seconds` | `60` | 一轮少于这个秒数不推"任务完成"。调小会让日常问答开始刷屏 |
| `min_interval_seconds` | `30` | 同一会话、同一类通知的最短间隔 |
| `message_style` | `minimal` | 「任务完成」带不带正文：`minimal` 不带（只剩五行）/ `collapsed` 正文折叠进可展开引用 / `full` 直接摊开。**只管这一类消息**，「需要你批准 / 回答」的正文是问题本身，永远带 |
| `show_activity` | `true` | 「任务完成」里加一行本轮用过的工具与改过的文件，从 transcript 数出来，不经过模型 |
| `separator` | `━━━━━━━━━━━━━━` | 每条消息顶部的分隔线，空串 = 不加。浅色主题下相邻消息挨太紧时靠它断开 |
| `gap_lines` | `1` | 每条消息尾部补几行空白（盲文空白字符，Telegram 不会裁掉），最多 5，0 = 不补 |
| `max_text_chars` | `700` | 正文截断长度（Telegram 上限 4096）。`message_style=minimal` 时对「任务完成」无效 |
| `skip_if_mac_active_seconds` | `0` | 大于 0：Mac 在这么多秒内有键鼠输入就不推**普通通知**。0 = 总是推 |
| `allowed_user_ids` | `[]` | 允许点按钮的 Telegram 用户 id。空 = 私聊对象本人；**群聊必须填**，否则远程批准整体关闭 |
| `events.stop` | `true` | 任务完成 |
| `events.permission_prompt` | `true` | 需要你批准（无按钮版；按钮版由 `approve` 控制，两者不会同时发） |
| `events.elicitation_dialog` | `true` | 需要你回答 |
| `events.agent_needs_input` | `true` | 子代理要输入 |
| `events.idle_prompt` | `false` | 空闲 60 秒提醒；和 Stop 重复，默认关 |
| `events.permission_denied` | `false` | auto 模式拒绝操作时推送 |
| `silent.<事件名>` | 无 | 设 `true` 则该类消息静音送达（Telegram 不响铃）。事件名同 `events` 的键 |
| `approve.enabled` | `true` | 是否发带按钮的批准消息 |
| `approve.wait_seconds` | `90` | 等按钮的时长。**改了要重新跑 `install`**，hook 超时 = 这个值 + 30 |
| `approve.skip_if_mac_active_seconds` | `60` | 触发时 Mac 在这么多秒内活跃就不发按钮、直接终端提示；也决定等待途中是否因碰键鼠而交回。0 = 总是发且不交回 |

环境变量（测试与多实例用）：

| 变量 | 覆盖 |
|---|---|
| `CLAUDE_TG_NOTIFY_CONFIG_DIR` | 配置目录，默认 `~/.config/claude-tg-notify` |
| `CLAUDE_TG_NOTIFY_STATE_DIR` | 状态目录，默认 `~/.cache/claude-tg-notify` |
| `CLAUDE_CONFIG_DIR` | Claude Code 配置目录，默认 `~/.claude`；`install` 写的是它下面的 `settings.json` |

查看生效配置：`./claude-tg-notify status`（token 打码显示）。
