# 待验收

1. 在全新的 Codex 桌面任务中执行一轮超过正式配置 `min_turn_seconds`（当前 60 秒）的任务，核对 Telegram 完成通知及 `~/.cache/codex-tg-notify/notify.log`。CLI 的同步 `Stop` 已完成真实发送验收。
2. 运行 `./codex-tg-notify test --approve` 并在手机上点“允许一次”和“拒绝”，确认终端打印对应的 Codex `PermissionRequest` 决定。
3. 在真实 Codex 会话中触发需要批准的命令，手机点按钮，确认 Codex 执行或拒绝与点击一致。Mac 活跃时先把 `approve.skip_if_mac_active_seconds` 设为 0。

以上需要真实 Telegram 网络和 Codex 客户端，离线测试不能替代。
