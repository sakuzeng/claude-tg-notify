# 变更记录

## 0.5.0 — 2026-09-25

- **人不在 Mac 前时，`min_turn_seconds` 不再适用**（`away_after_seconds`，默认 120 秒）。
  这个阈值的本意一直是"多久算你可能已经走开了" —— 那是拿耗时去**猜**，而 macOS 的空闲时间能直接测。
  在手机上驱动会话时没有终端可看，54 秒的回答一样需要推送；坐在 Mac 前时阈值照旧挡日常问答刷屏。
  探测不到空闲时间（非 macOS）时沿用阈值，不会突然开始刷屏。设 0 关闭。
  日志会写明原因：`sent stop for xxx (54s，你不在 Mac 前)`。
- 现场：2026-09-25 一天里有 6 条"任务完成"被 60 秒阈值吞掉，其中一条是 54 秒 —— 差 6 秒。
- 新增 [`docs/ops/TROUBLESHOOTING.md`](docs/ops/TROUBLESHOOTING.md)：日志每一行是什么意思、
  日志里什么都没有该查什么、两个空闲判断的方向差别。逐条对着代码里的 `config.log(...)` 写的。
- README 边界补上空闲检测的真实局限：它只知道你有没有碰键鼠，不知道你在不在看屏幕。

## 0.4.2 — 2026-09-25

- **修一轮的计时起点被静默重置。** `UserPromptSubmit` 不只在你敲回车时触发 —— 后台任务完成后
  注入会话的提示、排队发出的消息同样会触发它，而 `handle_user_prompt` 无条件重置 `started_at`，
  于是一轮的耗时被缩成最后一小段，**恰恰是会开后台 agent 的长任务最容易被 `min_turn_seconds` 拦掉**。
  现在起点只记一次，由 Stop 负责清空；超过 6 小时（`STALE_TURN_SECONDS`）视为上次 Stop 丢了，重新计时。
  现场与验算见 [`docs/ops/PITFALLS.md`](docs/ops/PITFALLS.md) 第 15 条。
- 中途被注入打断时写一行日志（`turn for <sid> already running Ns, keeping start`），
  这个事件原本什么都不记，出问题只能靠时间戳反推。
- 测试 130 → 135 条，含 2026-09-25 现场的回归用例。

## 0.4.1 — 2026-09-23

- 「这轮动了什么」里的文件名包进 `<code>`。裸着写会被 Telegram 自动识别成网址加链接
  （`.md` 是摩尔多瓦、`.py` 是巴拉圭的顶级域名），点一下跳浏览器。
  实测证据：同一段文字裸发回来带两个 `url` 实体，包进 `<code>` 只剩 `code`。
  顺带得到一块浅底，花纹壁纸上更好认。

## 0.4.0 — 2026-09-23

- **「任务完成」默认不再搬正文**（`message_style`，默认 `minimal`）。这个工具的本分是告诉你哪个做完了，
  不是把回复复述一遍。另两档：`collapsed`（正文折进 `<blockquote expandable>`，点开展开，已真机验证可用）、
  `full`（0.3.x 的行为）。只影响「任务完成」；「需要你批准 / 回答」的正文是问题本身，照旧。
- **新增一行「这轮动了什么」**（`show_activity`，默认开）：`🛠 Bash×20 Edit×7 Read×5 Write · config.py telegram.py +2`。
  顺着 transcript 数这一轮的 `tool_use` 记录得来，**只读文件、不经过模型、不产生 token**。
- **每条消息加了外壳**：顶部分隔线 `separator` 与尾部空白 `gap_lines`（默认 1 行，用 U+2800 盲文空白，
  Telegram 不会把它当空白裁掉）。浅色主题下相邻消息挨得太紧，而气泡间距归客户端主题管、bot 改不了，
  只能在消息内部制造边界。两个都能关。
- 测试 110 → 129 条。

## 0.3.1 — 2026-09-22

- `min_turn_seconds` 默认值从 30 秒提到 60 秒。实测下来 30 秒会让日常问答频繁触发通知，
  而这个阈值真正要回答的是"多久算你可能已经走开了"。已有配置文件不受影响。

## 0.3.0 — 2026-09-22

- **单文件拆成包**：`config` / `state` / `telegram` / `approval` / `handlers` / `install` / `cli` 七个模块，
  另加根目录垫片 `claude-tg-notify`，clone 下来仍免安装直跑。
- hook 入口从 `claude_tg_notify.py` 改为垫片；`install` 识别改为匹配 `claude_tg_notify` 与 `claude-tg-notify`
  两个标记，覆盖全部历史入口形态，**从 0.2.0 升级不会留下重复条目**。
- pip 安装且没有垫片时，hook 退回 `'<解释器绝对路径>' -m claude_tg_notify hook`。
- 测试从 20 条扩到 110 条：按模块分文件，新增文本构造单测、入口子进程测试、升级迁移测试，
  以及用 AST 守住"只用标准库 / 跨模块走模块对象 / 除 cli 外不许 print"的结构约束。
- `status` 在 `approve.wait_seconds` 与已安装 hook 超时不匹配时给出警告；`setup` 遇到群聊 chat id 时提示要填 `allowed_user_ids`。

## 0.2.0 — 2026-09-22

- **在 Telegram 上批准 / 拒绝**：`PermissionRequest` hook 发带 inline 按钮的消息，轮询 `getUpdates` 拿决定，
  通过 `hookSpecificOutput.decision` 交回 Claude Code；"始终允许"回显 `permission_suggestions`。
- 多会话并发等待：`poll.lock` + `inbox/<req>.json`，一个消费者分发所有点击。
- 人在 Mac 前不发按钮（`approve.skip_if_mac_active_seconds`）；等待途中碰键鼠即交回终端。
- 一轮结束后把本会话早先的"需要你处理"消息改写为"已处理"（`editMessageText`）。
- 按事件静音（`silent`，对应 `disable_notification`）。
- auto 模式拒绝通知（`PermissionDenied`，默认关）。
- `test --approve` 演练命令；`status` 显示远程批准配置。

## 0.1.0 — 2026-09-22

- `UserPromptSubmit` / `Stop` / `Notification` 三条 hook：任务完成（带耗时与最后回复）、需要你处理。
- 会话标题取 transcript 的 `custom-title`，没有则取首条提示。
- `setup` 自动探测 chat id；`install` / `uninstall` 幂等合并 `~/.claude/settings.json` 并备份。
