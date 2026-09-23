# 待办

每条写清：在哪（file:line 或命令）、为什么要紧、怎么验证。做完就删，不留"已完成"行。

## P0 让结论变准

- **在真机上点一次按钮。** `./claude-tg-notify test --approve`，盯着手机点"允许一次"，终端应打印
  `{"hookSpecificOutput": {…"behavior": "allow"}}`，Telegram 上原消息被改写成"已允许（<你的用户名>，来自 Telegram）"。
  为什么要紧：这是 0.2.0 的核心功能，目前只有假 Telegram 测试通过。
  验证点在 `claude_tg_notify/approval.py` 的 `handle_permission_request`（`wait_for_decision` 返回后的三个分支）。
- **在终端 default 模式会话里触发真实 `PermissionRequest`。** 五条 hook 已装好，直接 `claude --permission-mode default`，
  让它执行一个需要确认的命令，例如 `curl https://example.com`，锁屏后在手机上点。
  为什么要紧：hook 超时、`async` 缺省、stdout JSON 的解析都只在真实 Claude Code 里才能证实。
  验证：终端不弹提示直接执行；`~/.cache/claude-tg-notify/notify.log` 出现 `approve: allowed (a) by …`。
- **验证"始终允许"回显 `permission_suggestions` 后本会话确实不再询问。** 同上场景点第二排按钮，再让 Claude 执行同类命令。
  为什么要紧：`updatedPermissions` 的取法（优先 `destination == "session"`，否则第一条）是按文档推断的，见
  `handle_permission_request` 里 `session_scoped or suggestions[:1]`。
  验证：第二次同类命令没有权限提示、没有 Telegram 消息。

## P1 陷阱

- **`approve.wait_seconds` 改大后 hook 超时不会自动跟着变。** `our_hook_entries` 在 `install` 时把 `wait + 30` 写死进 settings.json。
  为什么要紧：用户改配置不重装，hook 会在决定回来前被 Claude Code 杀掉，表现为"点了没反应"。
  候选：`status` 检测两者不一致时警告；或 `install` 提示。验证：改 `wait_seconds` 为 200 后 `status` 有提示。
- **群聊场景 `allowed_user_ids` 为空时 `setup` 不提醒。** `cmd_setup` 拿到负数 chat id 时应当场提示要填这个列表，否则远程批准静默关闭（`handle_permission_request` 只写日志）。
  验证：`setup --chat-id -100123` 后终端有明确提示。

## P2 功能缺口

- **消息太长，想要"只提醒、不复述"。** 2026-09-23 用户提出：手机上只要知道"完成了"或"要你确认"，
  不需要把 Claude 的最后一段回复整段搬过去。现在 `max_text_chars` 默认 700，一条通知能刷满半屏。
  在哪：`claude_tg_notify/handlers.py:83`（任务完成拼装）、`:118`（需要你处理拼装）、`claude_tg_notify/telegram.py:24`（`truncate`）。
  **先澄清一个误解**：正文不花 token。它来自 hook 载荷里的 `last_assistant_message`，从磁盘读、直接发走，全程不过模型；
  所以代价只有"一屏看不完"，解法应当是折叠而不是砍掉信息。
  候选设计：新增 `message_style` 三档 —— `full`（现状）/ `collapsed`（正文包进 `<blockquote expandable>`，默认折叠成三行，点一下展开）/
  `minimal`（不带正文，只剩标题 + 会话 + 项目 + 耗时四行）。默认给 `collapsed`。
  为什么要紧：这是每天都在看的东西，长度直接决定它是工具还是噪音。
  验证：先确认 `<blockquote expandable>` 在 HTML parse mode 下真的可用（Bot API 7.0+ 才有；不可用就退回不可折叠的 `<blockquote>`）；
  再 `./claude-tg-notify test`，手机上默认三行以内、点开是全文，`message_style=minimal` 时消息里没有正文段。

- **浅色主题下相邻消息糊成一片。** 2026-09-23 用户提出：TG 白底时连续几条 bot 消息之间没有视觉边界，要逐字读才分得清哪条是哪条。
  在哪：同上的拼装处；格式的唯一事实源是 [`../guide/ARCHITECTURE.md`](../guide/ARCHITECTURE.md) 的「消息格式」，改了要同步。
  **bot 改不了的**：气泡颜色、聊天背景、字体 —— 那是 Telegram 客户端主题，只能用户自己长按聊天 →「更改壁纸/主题」单独设。
  这条属于使用提示，写进 README，不要当成待开发功能。
  **bot 能改的**（按性价比排）：
  1. 首行加色块前缀 `🟩 任务完成` / `🟨 需要你批准` / `🟥 被拒绝`，白底上是明确色带，改动最小；
  2. 正文包进 `<blockquote>`，Telegram 渲染成左竖线 + 浅底，天然把元信息和正文分块（与上一条的折叠方案是同一个改动）；
  3. 会话/项目/耗时压成一行 `<code>`，灰底，与正文形成明暗对比；
  4. 末尾一条 `<b>━━━━━━━━━━</b>` 分隔线，最土但最有效，留作备选。
  为什么要紧：通知的价值在于扫一眼就知道要不要处理，扫不出来等于没通知。
  验证：浅色主题下连发三条不同类型消息（`test`、`test --approve`、伪造一条 `permission_denied` 载荷），截图看三条边界是否一眼可辨。

- **Linux 空闲检测。** `mac_idle_seconds` 在非 darwin 直接返回 None，`skip_if_mac_active_seconds` 与 `approve.skip_if_mac_active_seconds` 在 Linux 上失效（总是发）。
  候选 `xprintidle`。验证：Linux 上 `status` 之外增加一条 `idle` 诊断输出。

## P3 组织

- **推到 GitHub 前把 README 快速开始里的仓库地址核对一遍**（`https://github.com/sakuzeng/claude-tg-notify`），并确认 CI 在 ubuntu + macOS × 3.9 / 3.12 全绿。
