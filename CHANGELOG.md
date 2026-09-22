# 变更记录

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
