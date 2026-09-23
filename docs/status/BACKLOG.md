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

- **0.4.0 的消息形态要在手机上用几天再定。** 已交付：`message_style=minimal`（默认）、一行「这轮动了什么」、
  顶部分隔线 `separator` + 尾部空白 `gap_lines=1`。在哪：`claude_tg_notify/telegram.py` 的 `decorate` 与 `turn_activity`、
  `claude_tg_notify/handlers.py:82` 起。
  还没定的：分隔线长度（现在 14 个 `━`）、`gap_lines` 到底 1 行够不够、工具那一行截到 4 种工具 3 个文件是否合适。
  为什么要紧：这几个数字只有在真实使用里才知道，改起来是一行配置，别凭空调。
  验证：连着用两天，如果还得眯眼找边界就把 `gap_lines` 调到 2；如果嫌吵就把 `separator` 清空。

- **Linux 空闲检测。** `mac_idle_seconds` 在非 darwin 直接返回 None，`skip_if_mac_active_seconds` 与 `approve.skip_if_mac_active_seconds` 在 Linux 上失效（总是发）。
  候选 `xprintidle`。验证：Linux 上 `status` 之外增加一条 `idle` 诊断输出。

## P3 组织

- **推到 GitHub 前把 README 快速开始里的仓库地址核对一遍**（`https://github.com/sakuzeng/claude-tg-notify`），并确认 CI 在 ubuntu + macOS × 3.9 / 3.12 全绿。
