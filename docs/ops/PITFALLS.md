# 踩坑记录

> 按日期追加，格式：现象 → 原因 → 解法 → 已回写代码：是/否。
> 跨项目通用的东西（Clash TUN、Telegram 代理）不在这里展开。

## 索引

| # | 日期 | 阶段 | 一句话 |
|---|---|---|---|
| 1 | 2026-09-22 | 官方推送 | 终端 `/config` 搜不到 push 选项：会话在用 API key 计费，推送只对 claude.ai 登录开放 |
| 2 | 2026-09-22 | 官方推送 | vivo 开着 Google 基础服务仍收不到，通知历史为空：FCM token 没注册上，这条路放弃 |
| 3 | 2026-09-22 | 官方推送 | 内置 `PushNotification` 在终端活跃时拒发，只能靠延时 cron 才测出链路是通的 |
| 4 | 2026-09-22 | hook | `UserPromptSubmit` 的 stdout 会进模型上下文 |
| 5 | 2026-09-22 | hook | `PermissionRequest` 在 auto 模式根本不触发 |
| 6 | 2026-09-22 | Telegram | `getUpdates` 单消费者；多会话同时等会互相吞点击 |
| 7 | 2026-09-22 | Telegram | 轮询偶发 `EOF occurred in violation of protocol (_ssl.c:1129)` |
| 8 | 2026-09-22 | 开发流程 | 用 Bash 里的 Python 补丁脚本改 hook 代码被 auto 模式分类器以 Self-Modification 拒绝 |
| 9 | 2026-09-22 | 演练 | `test --approve` 发出去了但 90 秒没人点，被误读为链路故障 |
| 10 | 2026-09-22 | 拆包 | 改 hook 入口文件名会让旧条目认不出来，升级后 settings.json 里留下重复 hook |
| 11 | 2026-09-22 | 拆包 | 旧的 `claude_tg_notify.py` 没删，setuptools 读版本号读到它，包版本停在 0.2.0 |
| 12 | 2026-09-22 | 拆包 | `from .telegram import send_message` 会让测试打桩静默失效 |

## 记录

### 1. `/config` 里没有 push 选项（2026-09-22，官方推送）
- 现象：终端 Claude Code 的 `/config` 搜 "push" 显示 `No settings match`。
- 原因：顶栏写着 `API Usage Billing`，这个终端在用 API key；Remote Control 与手机推送只对 claude.ai 账号登录的会话开放，选项被整个隐藏。
- 解法：`/login` 换成 claude.ai 账号；若环境里有 `ANTHROPIC_API_KEY` 它优先级更高，先注释掉。
- 已回写代码：否（不属本项目）。

### 2. vivo 收不到官方推送（2026-09-22，官方推送）
- 现象：Mac 侧 `Mobile push requested`，两个 push 开关都 true，没有 `No mobile registered` 警告；手机系统通知历史里没有任何 Claude 条目。
- 原因：官方推送走 FCM。vivo 国行即使打开"Google 基础服务"，FCM 要连 Google 服务器，没有代理就注册不上 token；服务器收到推送请求后静默丢弃。GitHub issue #57758（三星 S24）同样表现，关闭为重复，无修复。
- 解法：不修了。换一条不依赖 FCM 的通道，选型见 [`../research/PUSH_CHANNELS.md`](../research/PUSH_CHANNELS.md)。
- 已回写代码：是（整个项目）。

### 3. 内置推送工具在终端活跃时拒发（2026-09-22，官方推送）
- 现象：在会话里直接调 `PushNotification` 返回 `Not sent — this terminal is active`。
- 原因：设计如此，人在终端前就认为通知多余。测链路时人恰好就在终端前。
- 解法：用会话内 cron 延时 3 分钟再发，期间锁屏。这次才拿到 `Mobile push requested`，证明 Mac 侧无问题、卡点在手机。
- 已回写代码：否。本项目自己的通道不做这种判断（可选的 `skip_if_mac_active_seconds` 默认 0）。

### 4. `UserPromptSubmit` 的 stdout 是模型上下文（2026-09-22，hook）
- 现象：文档明写：该事件的纯文本 stdout "is added as context that Claude can see and act on"。
- 原因：这是给 hook 注入上下文的正式渠道，但对通知脚本是陷阱：随手 print 一行日志就会塞进对话。
- 解法：`run_hook` 对除 `PermissionRequest` 外的所有事件返回 `None`，`cmd_hook` 只在有返回值时才写 stdout；日志一律进文件。
- 已回写代码：是（`cmd_hook`、`run_hook`）。

### 5. `PermissionRequest` 不在 auto 模式触发（2026-09-22，hook）
- 现象：桌面 App 的会话用 auto 模式，装了 hook 也永远看不到按钮消息。
- 原因：官方文档："only fires in manual permission modes"；auto 模式由分类器决定，拒绝时走 `PermissionDenied`。
- 解法：接受。README 边界里写明；顺手加了默认关闭的 `permission_denied` 事件，auto 模式下至少能知道被拦了。
- 已回写代码：是（`handle_permission_denied`），文档见 [`../guide/HOOKS.md`](../guide/HOOKS.md)。

### 6. `getUpdates` 只允许一个消费者（2026-09-22，Telegram）
- 现象：设计阶段就能预见：两个会话各自 `getUpdates`，A 拉走的更新 B 永远看不到；A 又只认自己的 req，B 的点击就丢了。
- 原因：Bot API 的长轮询是"确认即消费"，offset 一推进别人就拿不到。
- 解法：`poll.lock` 互斥，拿到锁的那个 hook 把拉到的每条点击**按点击自带的 req** 写进 `inbox/`，其他 hook 只看自己的 inbox 文件。锁 45 秒无更新视为陈旧可抢。
- 已回写代码：是（`acquire_poll_lock` / `poll_callbacks_once` / `wait_for_decision`），有测试 `test_foreign_callback_is_filed_to_its_own_inbox`。

### 7. 轮询偶发 SSL EOF（2026-09-22，Telegram）
- 现象：日志 `poll failed: <urlopen error EOF occurred in violation of protocol (_ssl.c:1129)>`，出现一次，随后轮询恢复。
- 原因：代理链路上的瞬时断连，系统 Python 3.9 的 OpenSSL 报法就是这样。
- 解法：失败不推进 offset、sleep 2 再来。因为 Telegram 未被确认的更新会重发，点击不会丢。
- 已回写代码：是（`wait_for_decision` 的 except 分支）。

### 8. 改 hook 代码被分类器拒绝（2026-09-22，开发流程）
- 现象：Claude Code auto 模式下，用 `python3 - <<EOF` 给脚本打补丁的 Bash 命令被拒：`[Self-Modification]`。
- 原因：补丁内容包含"输出 allow 决定的 PermissionRequest hook"，分类器把它看成模型在改自己的权限机制。判断本身合理。
- 解法：改用 Edit / Write 工具改源码（可审计的编辑路径）；**把 PermissionRequest hook 写进 settings.json 这一步留给人跑 `install`**，模型不替人开这个口子。
- 已回写代码：否（流程约定）。

### 9. 演练"未响应"不等于链路坏（2026-09-22，演练）
- 现象：`test --approve` 打印 `未响应/交回终端`。
- 原因：日志显示 `asked … req 643c61f8c925` 成功、期间一次 SSL EOF 后恢复、90 秒到期；用脚本的 `getUpdates` 以已保存 offset 偷看，队列里没有迟到的点击，所以只是没人点。
- 解法：看日志的三行顺序（asked → poll failed → handed back）再下结论；重跑时盯着手机。
- 已回写代码：否。

### 10. 换 hook 入口名会留下重复条目（2026-09-22，拆包）
- 现象：0.3.0 把入口从 `claude_tg_notify.py` 换成垫片 `claude-tg-notify`。若识别逻辑仍只认旧文件名，
  升级时旧条目既删不掉也替换不了，settings.json 里每个事件会变成两条 hook，每次事件推两遍消息。
- 原因：`is_ours()` 靠命令串里的文件名判断"这条是不是我们装的"，入口改名就等于换了身份。
- 解法：识别改成匹配一组标记 `("claude_tg_notify", "claude-tg-notify")`，覆盖单文件、垫片、console script、
  `-m` 模块入口四种历史形态；两个标记都足够独特，不会误伤别人的 hook。迁移路径由测试钉住
  （`tests/test_install.py::MigrationTests`）。本机迁移后用 `jq` 核对过每个事件恰好一条。
- 已回写代码：是（`install.HOOK_MARKERS`）。

### 11. 旧文件没删导致版本号读错（2026-09-22，拆包）
- 现象：包里 `VERSION = "0.3.0"`，`pip show` 却报 0.2.0；而 console script 打印 0.3.0，两边不一致。
- 原因：`pyproject.toml` 用 `version = {attr = "claude_tg_notify.VERSION"}` 动态读版本。当时仓库根目录
  同时存在旧的 `claude_tg_notify.py`（0.2.0）与新的 `claude_tg_notify/` 包，setuptools 解析到了那个模块文件。
- 解法：删掉旧文件后重装，版本恢复 0.3.0。教训是**同名的模块与包不能并存**，哪怕只是过渡期。
  删之前先用 AST 比对两边的函数名集合，确认无遗漏再删。
- 已回写代码：否（一次性迁移）。

### 12. 拆包后测试打桩静默失效（2026-09-22，拆包）
- 现象：拆模块时如果写成 `from .telegram import send_message`，测试里 `mock.patch.object(telegram, "tg_api")`
  就打不中 —— 名字在导入时已经绑定。测试照样"通过"，但实际会真的发 HTTP 请求。
- 原因：Python 的 `from X import name` 是值绑定，不是引用。
- 解法：定死约定 —— 跨模块一律 `from . import telegram` 再 `telegram.send_message(...)`。
  这条约定由 `tests/test_layout.py::CallConventionTests` 用 AST 强制，写错直接测试失败。
- 已回写代码：是（全部模块 + 静态约束测试）。
