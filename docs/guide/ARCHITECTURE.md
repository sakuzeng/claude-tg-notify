# 架构与数据流

> 常青规范。描述包的运行时结构；改了代码要同步改这里。

## 一句话

Claude Code 在生命周期节点上以子进程方式调 `python3 <仓库>/claude-tg-notify hook`，
把事件 JSON 喂到 stdin；脚本读配置、读写每会话状态文件、调 Telegram Bot API；
只有 `PermissionRequest` 会往 stdout 写东西（决定），其余事件对 stdout 保持沉默。

## 模块

根目录的 `claude-tg-notify` 是垫片，只把自己所在目录放进 `sys.path` 再调 `cli.main`，
所以 clone 下来不安装也能跑。真正的代码在包里：

| 模块 | 职责 | 依赖 |
|---|---|---|
| `config` | 路径常量、日志、配置文件读写、macOS 空闲探测 | 无 |
| `state` | 每会话状态文件、同类节流、待处理消息登记 | `config` |
| `telegram` | Bot API 调用，以及消息文本怎么拼 | `config` |
| `approval` | 远程批准：按钮、轮询锁、inbox、决定输出 | `config` `state` `telegram` |
| `handlers` | 五个事件的处理与分发 | 以上全部 |
| `install` | 把 hook 合并进 `settings.json` | `config` `handlers` |
| `cli` | 命令行门面，唯一允许 print 的地方 | 以上全部 |

两条规矩由 `tests/test_layout.py` 机器守着：

- **只用标准库。** 新增依赖必须先改测试里的白名单，等于一道人工闸门。
- **跨模块调用走模块对象**（`telegram.send_message(...)`），不写 `from .telegram import send_message`。
  后者在导入时就把名字绑死，测试再打 `telegram.tg_api` 就打不中，桩会静默失效。

## 数据流

```text
Claude Code 会话
  │ UserPromptSubmit ──► 写 sessions/<sid>.json: started_at, cwd, first_prompt   （不联网）
  │ Stop ─────────────► 算耗时 ≥ min_turn_seconds ? sendMessage(任务完成) : 跳过
  │                     顺手 editMessageText 把 pending_msgs 改成"已处理"
  │ Notification ─────► sendMessage(需要你处理)，message_id 记进 pending_msgs
  │ PermissionRequest ► sendMessage(带 inline 按钮) ─► 等待 ─► stdout 输出 decision 或什么都不输出
  │ PermissionDenied ─► sendMessage(自动模式拒绝)（默认关）
  ▼
Telegram Bot API（api.telegram.org，可配 HTTP 代理）
```

## 磁盘上的东西

| 路径 | 内容 | 谁写 |
|---|---|---|
| `~/.config/claude-tg-notify/config.json` | token、chat id、阈值、开关；权限 600 | `setup`，人手改 |
| `~/.cache/claude-tg-notify/sessions/<sid>.json` | `started_at`、`cwd`、`first_prompt`、`last_sent{kind: ts}`、`pending_msgs[]`、`perm_handled_until` | 各 hook |
| `~/.cache/claude-tg-notify/inbox/<req>.json` | 一次按钮点击的决定：`choice` ∈ `a/s/d`、`from`、`at` | 拉到更新的那个 hook |
| `~/.cache/claude-tg-notify/poll.lock` | `getUpdates` 消费者互斥；内容是 pid；45 秒没更新视为陈旧 | 等待中的 hook |
| `~/.cache/claude-tg-notify/updates_offset` | 已确认的 `update_id + 1`，避免重复消费 | 拉更新的 hook、`setup` |
| `~/.cache/claude-tg-notify/notify.log` | 每次发送/跳过/失败一行；超过 1 MB 轮转一次 | 所有路径 |
| `~/.claude/settings.json` 的 `hooks` | 五条 hook；命令串含 `claude_tg_notify` 或 `claude-tg-notify`，据此识别"我们的"条目 | `install` / `uninstall` |

状态文件写入走 `tmp → replace`，同一会话的 hook 之间不会读到半截文件。

## 消息格式

统一 HTML parse mode，所有来自会话的文本经 `html.escape`。

每条消息出门前都过一遍 `telegram.decorate()`：顶部加 `separator` 分隔线，尾部补 `gap_lines` 行空白
（盲文空白 U+2800 —— Telegram 会裁掉消息首尾的普通空白，但不认它是空白）。
气泡颜色与间距归客户端主题管，bot 只能在消息内部制造边界，这两个开关就是为浅色主题下「几条糊成一片」准备的。

```text
━━━━━━━━━━━━━━                       ← separator
✅ <b>任务完成</b>
<b>会话</b>：<transcript 的 custom-title，没有则首条提示，截 80 字>
<b>项目</b>：<cwd 的最后一段>  <code>#<sid 前 8 位></code>
<b>耗时</b>：3 分 12 秒
🛠 Bash×20 Edit×7 Read×5 Write · CLAUDE.md config.py telegram.py +2   ← show_activity
⠀                                     ← gap_lines 行空白
```

`message_style` 决定要不要接正文（默认 `minimal` = 不接）：

| 值 | 正文 |
|---|---|
| `minimal` | 没有。消息固定五行，只回答「哪个会话做完了、花了多久、动了什么」 |
| `collapsed` | `<blockquote expandable>` 包住，手机上折叠成三行，点一下展开（Bot API 7.0+，2026-09-23 真机验证可用）|
| `full` | 直接跟在后面，截到 `max_text_chars` |

「做了什么」那一行由 `telegram.turn_activity()` 生成：顺着 transcript 扫这一轮（`timestamp >= started_at`）的
`tool_use` 记录，按工具名计数取前 4 种，再从 Edit / Write / MultiEdit / NotebookEdit 的 `file_path` 取前 3 个文件名。
**全程只读文件、不调模型、不产生 token。**

```text
🔔 <b>需要你批准</b>
<会话/项目两行>

<b>Bash</b>
<pre>npm test</pre>

<i>90 秒内未响应将交回终端处理</i>
[✅ 允许一次] [⛔ 拒绝]
[✅ 始终允许（不再询问）]        ← 只在 permission_suggestions 非空时出现
```

决定后原消息被改写：`✅ 已允许（saku，来自 Telegram）` / `⛔ 已拒绝（…）` / `⌛ 未响应，请在终端或 Claude App 里处理` /
`⌛ 检测到你在 Mac 前，…`，并去掉按钮。

`tool_summary` 取最能说明问题的那个参数：Bash 取 `command`，文件工具取 `file_path`，
Web 工具取 `url`/`query`，其余把 `tool_input` 整个 JSON 化；统一截 400 字。

## 远程批准的等待循环

```text
发消息（带按钮，callback_data = "p:<req 12 hex>:<a|s|d>"）
写 state.perm_handled_until = now + wait + 20      ← 让随后的 Notification(permission_prompt) 不再发无按钮版
loop until deadline:
    inbox/<req>.json 存在？ → 读走，跳出
    abort_on_mac_touch 且 HIDIdleTime < 3s？ → choice = "terminal"，跳出
    拿到 poll.lock？
        getUpdates(timeout=3, offset, allowed_updates=[callback_query])
        对每条 callback_query：
            推进 updates_offset
            data 不是 "p:*:*" → 忽略
            from.id 不在 allowed_user_ids → answerCallbackQuery("无权操作")，忽略
            否则写 inbox/<其 req>.json，answerCallbackQuery("已允许"/…)
        顺手清掉 inbox 里 10 分钟没人认领的文件
        释放锁
    否则 sleep 1
```

要点：

- 拉到的点击**按其自带的 req 归档**，不是按"当前正在等的 req"；所以谁拉都行。
- `getUpdates` 失败（网络、SSL EOF）不推进 offset，sleep 2 再来，点击不会丢。
- 超时或交回终端时消息会被改写并去掉按钮，用户点不到过期的按钮；万一 edit 失败、迟到的点击会进 inbox 然后被 10 分钟清理掉。
- `allowed_user_ids` 为空时：私聊取 `chat_id` 本身（私聊的 chat id 就是用户 id）；群聊（负数 id）视为空列表，整个远程批准功能关闭并写日志。

## 决定的输出

```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                        "decision": {"behavior": "allow"}}}
```

"始终允许"时加 `updatedPermissions`：优先回显 `destination == "session"` 的建议，没有就回显第一条。
拒绝时 `{"behavior": "deny", "message": "用户在 Telegram 上拒绝了这个操作"}`。
什么都不输出 = 交回 Claude Code 的正常提示流程。字段来源见 [`HOOKS.md`](HOOKS.md)。

## 空闲检测

`ioreg -c IOHIDSystem -d 4` 里的 `HIDIdleTime`（纳秒）。只有 macOS 有；其他平台返回 `None`，
所有"人在电脑前就跳过"的判断都视为不在，照发。

## 失败策略

hook 入口 `cmd_hook` 捕获一切异常，只写日志，返回 0。`sendMessage` 重试一次。
`editMessageText`、`answerCallbackQuery` 失败只记日志。设计目标是：**脚本再坏也不能让 Claude Code 卡住或报错**。
