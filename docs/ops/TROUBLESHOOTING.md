# 排查：这条为什么没发

> 这个项目几乎所有的疑问都是同一句话：「刚才那条怎么没推给我」。
> 答案几乎总在日志里 —— 每一次发送、跳过、失败都会留一行。**先看日志，再猜。**

```bash
./claude-tg-notify status              # 生效配置 + 装了哪几条 hook + 最近日志（token 打码）
tail -30 ~/.cache/claude-tg-notify/notify.log
```

## 日志行速查

| 日志里写着 | 意思 | 怎么办 |
|---|---|---|
| `sent stop for <sid> (123s)` | 发出去了，耗时 123 秒 | 手机没看到就去查网络/代理，不是本机的事 |
| `sent stop for <sid> (54s，你不在 Mac 前)` | 短于阈值，但 Mac 闲置够久，按「你不在电脑前」放行 | 正常 |
| `skipped stop: turn 54s < 60s` | 这一轮太短**且**判定你就在 Mac 前 | 想要它也推：调小 `min_turn_seconds`，或调小 `away_after_seconds` |
| `skipped stop: no start record for <sid>` | 这一轮没有起点。`/clear`、恢复旧会话、hook 装好之前就开着的会话都会这样 | 会话里发一条新消息即可恢复计时 |
| `turn for <sid> already running 232s, keeping start` | 一轮进行中又来了一条提示（后台任务通知 / 排队消息），起点保留 | 正常，这正是 PITFALL 15 的修复 |
| `skipped: Mac active 12s ago (< 60s)` | `skip_if_mac_active_seconds` 生效，人在电脑前不打扰 | 想一直推就把它设 0 |
| `skipped <事件>: sent 8s ago (< 30s)` | 同类通知节流 | 调 `min_interval_seconds` |
| `skipped permission_prompt: buttons message already sent` | 带按钮的版本刚发过，不再发无按钮的重复版 | 正常 |
| `not configured; run: claude-tg-notify setup` | 没填 token 或 chat id | 跑 `setup` |
| `send failed: <原因>` | 已重试一次仍失败，多半是网络或代理 | 检查 `proxy`；Clash TUN 模式留空 |
| `poll failed: <urlopen error EOF ...>` | 等按钮时轮询抖了一下 | 不用管，offset 不推进，点击不会丢（PITFALL 7）|
| `approve: Mac active 7s ago, leaving the prompt to the terminal` | 触发时你在 Mac 前，按钮消息不发，交给终端 | 想远程批准就把 `approve.skip_if_mac_active_seconds` 设 0 |
| `approve: handed back to terminal for <sid> (未响应)` | 等待超时没人点 | 调大 `approve.wait_seconds`，**改完必须重跑 `install`** |
| `activity scan failed: <原因>` | 「这轮动了什么」那一行没生成 | 不影响通知本身，消息照发 |
| `hook crashed: <异常>` | 脚本内部出错。hook 仍然返回 0，不会拖垮会话，但这条通知丢了 | 贴着异常来提 issue |
| `config unreadable: <原因>` | 配置文件坏了，**已静默退回全默认**（等于没配 token） | 修 `~/.config/claude-tg-notify/config.json` 的 JSON |
| `bad hook input: <原因>` | stdin 不是合法 JSON | 多半是手动灌数据时的手误 |
| `ignored event '<名字>'` | 收到了不处理的事件类型 | 正常；`install` 只装五种 |
| `approve: group chat without allowed_user_ids; set it in config` | chat 是群聊却没列白名单，**远程批准整体关闭** | 在 `allowed_user_ids` 里填你的 Telegram 用户 id |
| `rejected callback from user <id>` | 有人点了按钮但不在白名单里 | 确认这个 id 是不是你自己，是就加进去 |
| `approve: allowed (a) by <名字>` / `approve: denied by <名字>` | 按钮点成功了，决定已交回 Claude Code | 正常 |
| `sent <事件> for <sid>` | 「需要你批准 / 回答」一类通知发出去了 | 正常 |
| `edit failed` / `answerCallbackQuery failed` / `inbox write failed` | 收尾动作失败，尽力而为不影响主流程 | 偶发可忽略；反复出现查网络 |

> 这张表按代码里的 `config.log(...)` 逐条对过。新增跳过或失败路径时记得同步加一行。

## 日志里**什么都没有**

说明 hook 根本没被调用，按顺序查：

1. `./claude-tg-notify status` 看五条 hook 在不在。不在就 `install`。
2. `install` 写的是仓库垫片的**绝对路径**。仓库挪过位置就重跑一次。
3. 正在跑的会话要重启，或在会话里执行一次 `/hooks`。
4. 还是没有，就手动喂一次，看报什么错：

```bash
echo '{"hook_event_name":"Stop","session_id":"t","cwd":"/tmp","last_assistant_message":"hi"}' | python3 ./claude-tg-notify hook
```

## 「发得太慢了」

基本不会。Stop 在最后一段文字写完后 1–3 秒内触发，`Stop` 与 `Notification` 都是 `async`，
在后台发，不占会话时间。**觉得慢，先去日志里确认它到底发了没有** ——
本项目至今所有「怎么这么久还没来」的案例，真实原因都是被某条规则跳过了，一条都不是延迟。

## 两个空闲判断别搞混

| 配置 | 问的是 | 命中时 |
|---|---|---|
| `skip_if_mac_active_seconds` | 你**在**电脑前吗 | 在 → **不推**，别打扰 |
| `away_after_seconds` | 你**不在**电脑前吗 | 不在 → **推**，无视 `min_turn_seconds` |

两者方向相反。同时开启时 `skip_if_mac_active_seconds` **后判、优先**：
它要是把这条拦下了，前面的「不在电脑前」放行不算数。
两个都用的话，让 `skip_if_mac_active_seconds` ≤ `away_after_seconds`，否则中间那段区间的行为会反直觉。

探测手段是 `ioreg` 的 `HIDIdleTime`，只有 macOS 有。其他平台两个判断都返回「不成立」：
`skip_if_mac_active_seconds` 从不跳过（照发），`away_after_seconds` 从不放行（沿用阈值）。
两边都是保守方向 —— 不会因为探测不到就突然刷屏。
