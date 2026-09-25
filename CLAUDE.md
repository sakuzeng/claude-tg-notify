# claude-tg-notify 开发指南（每个会话必读）

把 Claude Code 的会话事件推到 Telegram，并能在 Telegram 上直接批准/拒绝工具调用。
**零第三方依赖**，macOS 自带 `python3` 直接跑；它自己就是装在 `~/.claude/settings.json` 里的 hook，
所以改坏了会立刻影响当前这台机器上所有 Claude Code 会话。

## 铁律（违反即事故）

1. **除 `cli` 外任何模块都不许 `print`。** `UserPromptSubmit` 的 stdout 会被当作上下文塞给模型；
   往里写东西 = 污染用户每一轮对话。唯一允许写 stdout 的是 `PermissionRequest` 的决定 JSON。
2. **hook 永远返回 0。** `cmd_hook` 捕获一切异常只写日志。这个脚本再坏也不能让 Claude Code 卡住或报错。
3. **只用标准库。** 加依赖要先改 `tests/test_layout.py` 的白名单，那道闸门是故意设的。
4. **跨模块调用走模块对象**（`telegram.send_message(...)`），不写 `from .telegram import send_message`。
   后者在导入时把名字绑死，测试打 `telegram.tg_api` 就打不中，桩会**静默失效**（PITFALL 12）。
5. **改 hook 入口的文件名或路径，必须同步 `install.HOOK_MARKERS`。** 认不出旧条目 = 用户升级后
   `settings.json` 里留下重复 hook，每个事件发两条消息（PITFALL 10）。改完跑 `tests/test_install.py::MigrationTests`。
6. **改动任何默认值要同时改四处**：`config.DEFAULT_CONFIG`、`config.example.json`、`docs/guide/CONFIG.md` 的表格、
   README 里提到该值的句子。版本号只有一个事实源：`claude_tg_notify/__init__.py` 的 `VERSION`，pyproject 动态读它。
7. **不要用 Bash 里的 Python 补丁脚本改本项目代码。** auto 模式的分类器会判定 Self-Modification 并拒绝
   （PITFALL 8）。用 Read / Edit / Write 工具改。
8. **发真消息会响用户的手机。** `test`、`test --approve` 以及任何直接调 Bot API 的验证，发之前先说一声。
9. **用户说"没收到"时，先查日志再改代码。** 每次发送/跳过/失败都有一行。
   至今所有"怎么这么慢还没来"的案例，真因都是被某条规则跳过了，**一条都不是延迟**。
   速查表在 [`docs/ops/TROUBLESHOOTING.md`](docs/ops/TROUBLESHOOTING.md)，新增跳过路径要同步加一行。

## 文档体系

索引在 [`docs/README.md`](docs/README.md)，原则是"每个问题只有一个去处"，不在第二处维护同一份内容。

| 想知道 | 去哪 |
|---|---|
| 现在处在哪、**哪些只是测试通过、哪些真机验证过** | [`docs/status/STATUS.md`](docs/status/STATUS.md) |
| 接下来做什么 | [`docs/status/BACKLOG.md`](docs/status/BACKLOG.md)（做完一条删一条，不留"已完成"行） |
| 模块划分、数据流、**消息格式**、并发设计 | [`docs/guide/ARCHITECTURE.md`](docs/guide/ARCHITECTURE.md) |
| 配置项与默认值 | [`docs/guide/CONFIG.md`](docs/guide/CONFIG.md) |
| Claude Code hook 契约：输入字段、输出格式、超时 | [`docs/guide/HOOKS.md`](docs/guide/HOOKS.md) |
| 某条消息为什么没发、日志每行什么意思 | [`docs/ops/TROUBLESHOOTING.md`](docs/ops/TROUBLESHOOTING.md) |
| 踩过的坑 | [`docs/ops/PITFALLS.md`](docs/ops/PITFALLS.md) |

**开工姿势**：先读 `STATUS.md` 的"已验证 / 未验证"表，再读 `BACKLOG.md`。
不要从对话历史里重建待办 —— 待办在磁盘上。

## 环境与命令

```bash
python3 -m unittest discover -s tests          # 140 条离线测试，全部用假 Telegram，不会真发消息
./claude-tg-notify status                      # 生效配置、装了哪几条 hook、最近日志（token 打码）
./claude-tg-notify install                     # 把 5 条 hook 合并进 ~/.claude/settings.json（先备份，幂等）
tail -30 ~/.cache/claude-tg-notify/notify.log  # 每次发送/跳过/失败一行，排查第一站
```

- 真实配置在 `~/.config/claude-tg-notify/config.json`（**不在仓库里**，权限 600，含 bot token）。
  用户改自己的配置 ≠ 仓库要改；要让新装的人也得到这个行为，才动 `DEFAULT_CONFIG`。
- 测试隔离靠三个环境变量：`CLAUDE_TG_NOTIFY_CONFIG_DIR`、`CLAUDE_TG_NOTIFY_STATE_DIR`、`CLAUDE_CONFIG_DIR`，
  `tests/helpers.py` 在 import 包之前就设好，顺序不能调。
- `install` 写的是根目录垫片的**绝对路径**，仓库挪位置就重跑一次。

## 关于 token

通知正文来自 hook 载荷（`last_assistant_message`）和 transcript 文件，读磁盘直接发走，**不经过模型，不产生 token**。
唯一有 token 成本的路径是 `PermissionRequest` 拒绝时回给 Claude Code 的 `message` 字段（几十个字）。
所以"消息太长"是阅读体验问题，不是费用问题，解法是折叠不是删信息。

## 工作节奏

改动即提交，中文 commit 信息，形如 `0.3.1：任务完成阈值默认值从 30 秒提到 60 秒`。
行为有变要写 `CHANGELOG.md`；`docs/guide/` 是常青规范，改代码同步改；
新踩的坑按"现象 → 原因 → 解法 → 已回写代码"追加进 `PITFALLS.md`，并在文首索引表加一行。
推 GitHub 前确认 CI（ubuntu + macOS × 3.9 / 3.12）全绿。
