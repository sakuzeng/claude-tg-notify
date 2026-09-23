# 边界与路线图

## 做什么、不做什么

**做**：Claude Code 单机 → Telegram 的通知，以及一次性的允许/拒绝决定。

**不做**：

- 从 Telegram 给会话发新指令、看会话输出。这是 Remote Control 的事。
- 多台机器共用一个 bot。`getUpdates` 单消费者决定了这需要一个常驻分发进程或 webhook，超出"一个文件零依赖"的定位。
- Windows。hook 命令串是 POSIX shell 形式，空闲检测只有 macOS。

## 已交付

- 0.1.0：任务完成 / 需要你处理 通知。
- 0.2.0：Telegram 上批准/拒绝、旧消息标记已处理、按事件静音、auto 模式拒绝通知。
- 0.3.0：拆成包（七模块 + 免安装垫片），测试扩到 110 条并加结构约束，升级迁移不留重复 hook。

## 候选下一步（按价值排）

1. **真实环境验证按钮路径**。目前只有假 Telegram 的测试和一次没人点的演练。在终端 default 模式会话里触发一次真的 `PermissionRequest`，
   确认 `updatedPermissions` 回显后本会话确实不再询问。这是 [`../status/BACKLOG.md`](../status/BACKLOG.md) 的 P0。
2. **消息形态：可折叠正文 + 视觉分隔**。用户 2026-09-23 提的两条：消息太长、浅色主题下分不清边界。
   正文折叠（`<blockquote expandable>`）与色块前缀是同一处改动，一起做。明细与验证方法见 [`../status/BACKLOG.md`](../status/BACKLOG.md) P2。
3. **常驻 bot 命令**：`/sessions`（列最近活跃会话）、`/mute 2h`、`/last`（重发上一条）。需要 launchd 守护进程，
   并把 `getUpdates` 消费者统一到守护进程、hook 改为向它询问决定。做了这一步，"多台机器共用 bot"也顺带解决。
4. **`setMyCommands` / `setMyDescription`**：给 bot 一个命令菜单和说明。只有 3 做了才有意义。
5. **Linux 空闲检测**：`xprintidle` 或 `loginctl`，让 `skip_if_mac_active_seconds` 在 Linux 上也生效。
6. **会话深链**：消息里放能直接打开该会话的 claude.ai 链接。目前 hook 输入里没有这个 URL，需先确认可推导。
