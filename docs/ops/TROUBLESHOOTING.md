# 通知排查

先运行 `./codex-tg-notify status`，再看 `~/.cache/codex-tg-notify/notify.log`。`status` 遮住 bot token，显示配置路径、四条 hook 的安装状态与最近日志。

| 日志或现象 | 原因与处理 |
|---|---|
| 没有新日志 | hook 未运行。检查 `status`、Codex `/hooks` 是否信任、当前会话是否在安装前启动 |
| `not configured` | 运行 `setup`；可用 `status` 核对新旧配置文件路径 |
| `skipped stop: no start record` | 未记录到本轮 `UserPromptSubmit`；发新提示后再验收，检查对应 hook 是否信任 |
| `skipped stop: turn … < …` | 时长低于 `min_turn_seconds`，且 Mac 未达到闲置阈值；调小阈值可验收短轮 |
| `skipped stop: duplicate turn` | 同一 `turn_id` 的 Stop 重复触发，已去重 |
| `skipped stop: turn mismatch` | 异步 Stop 与下一轮状态交错；旧轮消息已跳过，检查是否频繁出现 |
| `skipped: Mac active …` | `skip_if_mac_active_seconds` 设置了活跃时跳过；设 0 可总是推 |
| `approve: Mac active …` | 批准交给 Codex 本地界面；把 `approve.skip_if_mac_active_seconds` 设 0 可演练按钮 |
| `approve: handed back … (未响应)` | Telegram 等待超时；加大 `approve.wait_seconds` 后重新 `install` |
| `approve: group chat without allowed_user_ids` | 群聊须显式填写 Telegram 用户 id 白名单 |
| `rejected callback from user …` | 点击者不在白名单，或按钮数据无效 |
| `send failed` / `poll failed` | Telegram 网络或代理问题；检查 `proxy` 和 Telegram 连通性 |
| `hook crashed` | 处理器异常已被捕获；保留日志并提交问题 |

手动验证入口（不会发 Telegram，因没有开始记录）：

```bash
echo '{"hook_event_name":"Stop","session_id":"manual","turn_id":"t","cwd":"/tmp"}' | ./codex-tg-notify hook
```

`./codex-tg-notify test` 和 `test --approve` 会发送真实 Telegram 消息。`Stop` hook 运行于后台，通常不拖慢 Codex；手机未收到时先看日志，区分“跳过”与“发送失败”。
