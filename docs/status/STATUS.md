# 当前状态

**更新时间**：2026-09-23
**版本**：0.4.1（唯一事实源是 `claude_tg_notify/__init__.py` 的 `VERSION`，pyproject 动态读它）

## 一句话现状

七模块的包，129 条离线测试全过，打包与两种入口都在干净 venv 里验证过。
0.4.0 把「任务完成」改成默认只报五行（会话 / 项目 / 耗时 / 这轮动了什么），正文要看得自己开 `collapsed` 或 `full`。
消息可读性到此收口：**bot 侧该做的都做了，剩下的是客户端主题的事**（PITFALL 14 记了试过什么、为什么不再试）。
本机五条 hook 已迁移到新入口并用真实命令做过管道测试。
**按钮批准的真机路径仍然没有人点过** —— 这是唯一的功能性空白。

> 待办一律看 [`BACKLOG.md`](BACKLOG.md)，本文不维护第二份。

## 已验证 / 未验证

| 项 | 状态 | 证据 |
|---|---|---|
| Mac → Telegram 发消息 | ✅ | `test` 命令；日志里的 `sent stop for <sid> (41s)` 来自真实 Stop hook |
| 真实 hook 在桌面 App 会话里触发 | ✅ | settings.json 改后未重启，日志出现多次 Stop 触发记录 |
| Notification 路径（无按钮版）| ✅ | 用真实 transcript 喂 `permission_prompt` 载荷，手机收到带会话标题的消息 |
| 会话标题取自 transcript `custom-title` | ✅ | 同上，标题正确 |
| 按钮消息发出、超时改写、按钮消失 | ✅ | `test --approve`：日志 `asked → poll failed(1 次, 恢复) → handed back (未响应)` |
| 拆包后功能不变 | ✅ | 130 条测试全过，含原有全部行为断言 |
| `<blockquote expandable>` 真的能用 | ✅ | 2026-09-23 真机探测：sendMessage 接受该标签 |
| minimal 形态 + 「这轮动了什么」那一行 | ✅ | 用真实 transcript 走完整 hook，手机收到五行消息，stdout 为空 |
| 文件名不再被当成链接 | ✅ | `sendMessage` 返回的 `entities`：裸发 `['url','url']`，包 `<code>` 后 `['code']` |
| `message_style=collapsed` 真机可用 | ✅ | 手机上折叠成三行、右下角可展开；作者本机配置已切到这一档 |
| 免安装垫片与 `-m` 模块入口 | ✅ | `tests/test_entrypoint.py` 用子进程真实执行两种入口 |
| 打包元数据与 console script | ✅ | 干净 venv `pip install .` 后 `pip show` 与 `--version` 均为 0.3.0 |
| 从 0.2.0 升级不留重复 hook | ✅ | 本机实迁移，`jq` 核对每个事件恰好 1 条、0 条旧路径残留；另有迁移测试 |
| **按钮点击 → 决定交回 Claude Code** | ❌ 未在真机验证 | 只有假 Telegram 测试；演练时 90 秒内无人点，队列无迟到点击 |
| "始终允许"的 `updatedPermissions` 被 Claude Code 接受 | ❌ 未验证 | 字段格式按官方文档，未实测 |
| `PermissionRequest` hook 在终端 default 模式真实触发 | ❌ 未验证 | 已装入，但没在手动权限模式的会话里跑过 |
| Linux 上运行 | ❌ 未验证 | 无 macOS 专属调用（`ioreg` 失败即返回 None），CI 矩阵含 ubuntu 但尚未推送 |

## 入口

| 想知道 | 去哪 |
|---|---|
| 生效配置、hook 装了哪几条、最近日志 | `./claude-tg-notify status` |
| 测试 | `python3 -m unittest discover -s tests -v` |
| 模块划分与数据流 | [`../guide/ARCHITECTURE.md`](../guide/ARCHITECTURE.md) |
| 踩过的坑 | [`../ops/PITFALLS.md`](../ops/PITFALLS.md) |
