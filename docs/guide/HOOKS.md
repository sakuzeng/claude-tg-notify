# 用到的 Claude Code hook 契约

> 常青规范。以下字段与行为核对自 Claude Code 官方 hooks 参考（`code.claude.com/docs/en/hooks`），
> 核对日期 2026-09-22，对应 Claude Code v2.1.258。官方改了以官方为准，这里同步更新。

## `install` 写入的五条

| 事件 | matcher | 同步/异步 | 超时 | 我们做什么 |
|---|---|---|---|---|
| `UserPromptSubmit` | 无 | 同步 | 10 s | 只写状态文件：`started_at`、`cwd`、首条提示 |
| `Stop` | 无 | `async: true` | 30 s | 任务完成通知；把 `pending_msgs` 改成"已处理" |
| `Notification` | `permission_prompt\|elicitation_dialog\|agent_needs_input\|idle_prompt` | `async: true` | 30 s | 需要你处理（无按钮版） |
| `PermissionRequest` | 无 | **同步** | `approve.wait_seconds + 30` | 带按钮的批准；输出 decision |
| `PermissionDenied` | 无 | `async: true` | 30 s | auto 模式拒绝通知 |

五条命令串完全相同：`python3 '<仓库>/claude-tg-notify' hook`，按 stdin 里的 `hook_event_name` 分发。
pip 安装且没有仓库垫片时，退回 `'<解释器绝对路径>' -m claude_tg_notify hook`。

`install` 用命令串里是否含 `claude_tg_notify` 或 `claude-tg-notify` 识别自己的条目，替换而不重复追加；
其他人的 hook 原样保留。两个标记覆盖了所有历史入口形态，所以从 0.2.0 的单文件升级上来不会留下重复条目。

## 各事件 stdin 里我们用到的字段

| 事件 | 字段 |
|---|---|
| 所有 | `session_id`、`cwd`、`transcript_path`、`hook_event_name`、`agent_id`（子代理内才有，有则忽略该事件） |
| `UserPromptSubmit` | `message`（用户提示原文） |
| `Stop` | `last_assistant_message`（本轮最后一段回复） |
| `Notification` | `notification_type`、`title`、`message` |
| `PermissionRequest` | `tool_name`、`tool_input`、`permission_suggestions[]`、`permission_mode` |
| `PermissionDenied` | `tool_name`、`tool_input` |

`Notification` 的 `notification_type` 全集（2026-09-22）：`permission_prompt`、`idle_prompt`、`auth_success`、
`elicitation_dialog`、`elicitation_url_dialog`、`elicitation_complete`、`elicitation_response`、
`agent_needs_input`、`agent_completed`、`quota_auto_resume_fired`、`quota_auto_resume_stale`、`quota_auto_resume_disabled`。
我们只订阅四个。

## 输出契约

- **`UserPromptSubmit` 的 stdout 会被当作上下文塞给模型**。脚本对这个事件绝不输出。
- `Notification` 的输出被整个丢弃。
- `Stop` 退出码 2 会阻止 Claude 停下；我们永远退出 0。
- `PermissionRequest`：退出码 2 **不被承认**，只有 stdout 里的 `decision` 对象能允许或拒绝：

```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                        "decision": {"behavior": "allow" | "deny",
                                     "updatedInput": {…},          // allow 可选：整个替换工具输入
                                     "updatedPermissions": […],    // allow 可选：可原样回显 permission_suggestions
                                     "message": "…",               // deny 可选：告诉 Claude 为什么
                                     "interrupt": true}}}          // deny 可选：直接停掉 Claude
```

  什么都不输出（或输出不合法 JSON）= 正常权限提示照常弹出。
  hook 的 `allow` 不能越过用户设置里的 deny / ask 规则。
- `PermissionDenied` 可输出 `{"hookSpecificOutput": {"hookEventName": "PermissionDenied", "retry": true}}` 让模型重试；我们不输出。

## 触发条件里容易踩的

- **`PermissionRequest` 只在手动权限模式触发**（default / plan / acceptEdits / dontAsk）。auto 模式没有权限提示，
  只有分类器拒绝时的 `PermissionDenied`。
- `Stop` 在每一轮结束都触发，包括 `/clear`、恢复会话等，所以必须靠 `started_at` 有无来过滤。
- `async: true` 的 hook 一样收到 stdin，只是 Claude Code 不等它结束。
- settings.json 改动后，官方说法是运行中的会话需重启或执行 `/hooks`；实测桌面 App 的会话下一轮就触发了新 hook。
