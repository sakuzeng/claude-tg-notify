# claude-tg-notify

把 Claude Code 的会话事件推到 Telegram，并能在 Telegram 上**直接批准或拒绝**工具调用。
零第三方依赖，macOS 自带的 `python3` 就能跑，clone 下来免安装直接用。

| 消息 | 何时 |
|---|---|
| ✅ 任务完成 | 一轮对话结束且跑了超过阈值（默认 60 秒）；五行：会话、项目、耗时，外加一行「这轮动了什么」（工具计数 + 改过的文件）|
| 🔔 需要你批准（带按钮） | Claude 要执行需确认的操作；**允许一次 / 拒绝 / 始终允许** 三个按钮，点一下决定就交回 Claude Code |
| ❓ 需要你回答 / 输入 | AskUserQuestion 之类的提问、子代理等输入 |
| ⛔ 自动模式拒绝了操作 | auto 模式下分类器拦截了工具调用（默认关） |

每条带会话标题、项目名、会话 id。一轮结束后，之前的"需要你处理"会被改写成"已处理"，不会留一堆看起来还在等你的旧消息。

## 为什么是这样

- **为什么不用 Claude 官方的手机推送。** 官方推送走 Google 的 FCM。国产 ROM 上即使开了 Google 基础服务，
  推送 token 也常注册不上，手机系统通知历史里一条都没有，且必须全局代理。
  Telegram 官网 APK 用自己的长连接收消息，不依赖 FCM，代理只需在 Telegram 内设一个。
  候选通道的完整比较见 [`docs/research/PUSH_CHANNELS.md`](docs/research/PUSH_CHANNELS.md)。
- **为什么零依赖、还留一个根目录垫片。** hook 是 Claude Code 在裸子 shell 里调的，PATH 和 venv 都不可靠。
  `install` 把垫片的**绝对路径**写进 `~/.claude/settings.json`，用系统 `python3` 调，什么环境都能起；
  垫片只做一件事，把自己所在目录放进 `sys.path`，所以不装也能跑。pip 装过的话退回用解释器绝对路径调模块入口。
- **为什么"任务完成"有 60 秒阈值。** Stop 在每一轮结束都触发，包括三秒钟的问答；不设阈值就是刷屏。
  这个值的含义是"多久算你可能已经走开了"，所以宁可高不宜低。
- **为什么「任务完成」默认不带正文。** 这个工具只要回答一句话：哪个会话做完了。正文搬过来会占掉半屏，
  真正有用的是那一行 `🛠 Bash×20 Edit×7 · config.py telegram.py`，扫一眼就知道这轮干了什么。
  想看全文把 `message_style` 改成 `collapsed`（折叠，点开展开）或 `full`。
- **为什么它话多也不花钱。** 消息里所有内容都来自 hook 载荷和 transcript 文件，读磁盘、直接发走，
  **全程不经过模型，不产生 token**。所以取舍只在「你手机上的一屏」，不在费用。
- **为什么 Stop 和 Notification 是 async，PermissionRequest 是同步。** 只有"决定"需要阻塞会话；
  通知类 hook 在后台发，任何错误只写日志，永远返回 0，不会拖慢或打断 Claude Code。
- **为什么等按钮时要加锁。** Telegram 的 `getUpdates` 只允许一个消费者。多个会话同时在等，谁拿到锁谁拉更新，
  按请求 id 把决定放进 `inbox/`，其他会话各自认领；否则会互相吞掉对方的点击。
- **为什么人在 Mac 前就不发按钮。** 同步 hook 会挡住终端提示。hook 触发时若 Mac 60 秒内有键鼠输入，
  直接走终端；等待途中碰了键鼠也立刻交回。设计细节见 [`docs/guide/ARCHITECTURE.md`](docs/guide/ARCHITECTURE.md)。

## 快速开始

```bash
git clone https://github.com/sakuzeng/claude-tg-notify.git
cd claude-tg-notify
./claude-tg-notify setup      # 粘贴 @BotFather 给的 token，再给 bot 发一条消息
./claude-tg-notify install    # 把 5 条 hook 合并进 ~/.claude/settings.json（先备份，幂等）
./claude-tg-notify test       # 普通消息
./claude-tg-notify test --approve   # 带按钮的批准演练，手机上点，终端打印交给 Claude Code 的决定
```

`install` 写的是垫片的绝对路径，仓库挪了位置就重新跑一次。
也可以 `pip install .` 得到同名的 `claude-tg-notify` 命令，行为完全一样。

正在运行的 Claude Code 会话要重启，或在会话里执行一次 `/hooks`，新 hook 才生效
（实测桌面 App 的会话不重启也会立刻触发，但别依赖这一点）。

## 目录

| 路径 | 内容 |
|---|---|
| `claude-tg-notify` | 命令行与 hook 入口垫片，免安装直跑 |
| `claude_tg_notify/` | 包：`config` 路径与配置、`state` 会话状态与节流、`telegram` API 与文案、`approval` 远程批准、`handlers` 事件分发、`install` 写 settings.json、`cli` 命令行 |
| `tests/` | 130 条离线测试：假 Telegram 跑通全部路径，加入口子进程测试与包结构静态约束。`python3 -m unittest discover -s tests` |
| `config.example.json` | 配置项全集与默认值，真实配置在 `~/.config/claude-tg-notify/config.json` |
| `docs/guide/` | 常青规范：架构与数据流、配置项、用到的 Claude Code hook 契约 |
| `docs/ops/` | 踩坑记录 |
| `docs/research/` | 调研快照：推送通道选型 |
| `docs/plan/` | 边界与路线图 |
| `docs/status/` | 现在处在哪 / 接下来做什么 |

文档索引见 [`docs/README.md`](docs/README.md)。

## 边界

- 按钮批准只在**手动权限模式**下有用。auto 模式不弹权限提示，也就没有按钮消息，那里只有任务完成通知与默认关闭的拒绝通知。
- 不能从 Telegram 给会话发新指令。那是 Remote Control 的事，本项目只做"通知 + 一次性决定"。
- 一个 bot 只服务一台机器。`getUpdates` 单消费者的限制决定了两台 Mac 共用一个 bot 会互相吞点击。
- 手机得能连上 Telegram。这一条在国内意味着 Telegram 内要设代理。
- 空闲检测只在 macOS 上有（`ioreg`）。Linux 上视为"不在电脑前"，总是发。
- **Bot API 里没有任何颜色或样式参数。** 能发的只有粗体、等宽、引用、链接这类"这段是什么"的标记，
  具体长什么样（气泡颜色与透明度、引用块的底、字色、消息间距）全由 Telegram 客户端主题决定。
  消息在花纹壁纸上看不清，是半透明气泡把壁纸透上来了,这个问题只能在客户端解决：
  给该聊天单独换纯色壁纸、换主题，或导出 `.attheme` 自己改。
  bot 侧能做的只有在消息内部制造边界：顶部分隔线（`separator`）、尾部空白（`gap_lines`）、
  关键片段包 `<code>`。详见 [`docs/ops/PITFALLS.md`](docs/ops/PITFALLS.md) 第 14 条。

## License

MIT，见 [LICENSE](LICENSE)。
