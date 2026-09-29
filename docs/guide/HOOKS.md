# Codex hook 契约

核对来源：[Codex Hooks 官方文档](https://learn.chatgpt.com/docs/hooks)，2026-09-29。运行时行为以当前 Codex 版本和官方文档为准。

`install` 合并四条命令到 `~/.codex/hooks.json`。每条命令指向仓库根目录的 `codex-tg-notify hook`；pip 安装且垫片不存在时使用 `python -m claude_tg_notify hook`。

| 事件 | 同步/异步 | 超时 | 本项目用途 |
|---|---|---|---|
| `UserPromptSubmit` | 同步 | 10 秒 | 从 `prompt`、`session_id`、`turn_id` 记录首条提示与起点 |
| `PostToolUse` | 同步 | 10 秒 | 从 `tool_name`、`tool_use_id`、`tool_input` 记录工具名及文件名 |
| `Stop` | `async: true` | 30 秒 | 从 `last_assistant_message` 构造完成通知，按阈值决定是否发送 |
| `PermissionRequest` | 同步 | `approve.wait_seconds + 30` | 发按钮并等待；输出一次允许或拒绝的决定 |

四类事件共享 `session_id`、`cwd`、`hook_event_name`；与一轮相关的事件还提供 `turn_id`。`transcript_path` 虽然存在，但官方声明格式不稳定，所以本项目不读取它。`PostToolUse` 的 `apply_patch` 输入可包含补丁命令；本项目只提取文件名，不保存补丁正文。

`PermissionRequest` 只在 Codex 准备弹出批准请求时触发。若手机未响应，hook 不输出决定，Codex 继续其正常批准流程。Codex 当前接受：

```json
{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}
```

或 `behavior: "deny"`，可附 `message`。官方明确说明 `updatedInput`、`updatedPermissions`、`interrupt` 尚不受支持，因此不提供“始终允许”按钮。

Codex 没有对应旧版 Claude `Notification`、`PermissionDenied` 的 hook。`SessionEnd` 代表会话结束或空闲关闭，不代表一轮任务完成，不能用来替代 `Stop`。

Codex 会加载各配置层的匹配 hook，并要求审查与信任非托管 hook。`install` 只替换本项目命令对应的条目，保留其他条目。安装后在 Codex CLI 使用 `/hooks` 审查与信任。
