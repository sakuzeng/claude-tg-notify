# 推送通道选型（2026-09-22）

> 调研快照。问题：Claude Code 在 Mac 上跑长任务，人在外面用 vivo 手机远程控制，任务完成或需要确认时怎么让手机响。
> 结论：**Telegram Bot**。被推翻时在此处加更新块，不删原文。

## 约束

1. 手机是 vivo 国行，"Google 基础服务"开着但 FCM 推送注册不上（官方推送实测收不到，见 [`../ops/PITFALLS.md`](../ops/PITFALLS.md) #2）。
2. Mac 常开 Clash TUN，能直连境外 API；手机不想开全局 VPN。
3. 要两种消息：任务完成、需要确认。后者最好能**在手机上直接答**。
4. 零运维：不想自建服务器，不想付费。

## 候选

| 通道 | 手机端依赖 | 能否"直接答" | 免费额度 | 国内可达 | 结论 |
|---|---|---|---|---|---|
| Claude 官方 Remote Control 推送 | Claude App + FCM（Google Play 服务 + 代理） | 能（打开 App 批准） | 无限 | 差：FCM 需代理，vivo 注册失败 | ✗ 实测不通 |
| Server酱 Turbo | 微信 | 否 | **5 条/天**，3 元/月 1000 条/天 | 好 | 通知够用但没法批准，额度紧 |
| wecomchan（企业微信 → 微信） | 微信 | 否 | 基本无限 | 好 | 要注册企业微信，配置多几步；不能批准 |
| ntfy | ntfy App（F-Droid 版不需要 FCM） | 有 action 按钮，但回调要自己收 | 公共服务器免费 | 一般 | 可行，但回调要自建 HTTP 端点 |
| Bark | 仅 iOS | 否 | 免费 | 好 | ✗ 安卓不可用 |
| **Telegram Bot** | Telegram（官网 APK 自带长连接，**不需要 FCM**） | **能**：inline 按钮 + `getUpdates` 长轮询，Mac 主动拉，不用公网端点 | 无限 | 手机端要在 Telegram 内设代理 | ✓ |

## 为什么是 Telegram

- 唯一一个**手机端不依赖 FCM、Mac 端不需要公网可达**还能把决定收回来的通道。`getUpdates` 是 Mac 主动拉，
  按钮点击作为 `callback_query` 回来，整个回路都是 Mac 出站连接。
- Bot API 就是 HTTPS + JSON，标准库 `urllib` 足够，不引入依赖。
- 代价：手机必须能连 Telegram。用户本来就在用，接受。

## 官方推送为什么放弃而不是修

排查顺序与证据：Mac 侧 `Claude Max` 登录、`Push when Claude decides` / `Push when actions required` 均 true、
`/config` 无 `No mobile registered`、会话内 `PushNotification` 经 cron 延时后返回 `Mobile push requested`。
手机侧通知历史无任何 Claude 条目。GitHub issue #57758（Android，S24）同表现，被关为重复，无修复。
剩下的可能是 FCM 注册需要代理常开 + 重装刷新 token，即使修好也要求手机全局代理，不满足约束 2。

## 来源

- Claude Code Remote Control 文档：<https://code.claude.com/docs/en/remote-control>（Mobile push notifications 一节）
- anthropics/claude-code#57758：Android push notifications not working with remote control
- anthropics/claude-code#60208：Push notifications broken - mobile devices not receiving notifications
- Server酱 Turbo：<https://sct.ftqq.com/>（免费 5 条/天）
- wecomchan：<https://github.com/easychen/wecomchan>
- Telegram Bot API：<https://core.telegram.org/bots/api>（`sendMessage`、`editMessageText`、`getUpdates`、`answerCallbackQuery`）
