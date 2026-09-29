# 文档索引

每个问题只有一个去处，不在第二处维护同一份内容。

| 想知道 | 去哪 |
|---|---|
| 这是什么、为什么这样设计、怎么装 | [`../README.md`](../README.md) |
| 改这个仓库之前要知道的约定与命令 | [`../AGENTS.md`](../AGENTS.md) |
| 现在处在哪、哪些已验证哪些没有 | [`status/STATUS.md`](status/STATUS.md) |
| 接下来做什么 | [`status/BACKLOG.md`](status/BACKLOG.md)（做完一条就删一条） |
| 数据流、状态文件、消息格式、并发设计 | [`guide/ARCHITECTURE.md`](guide/ARCHITECTURE.md) |
| 每个配置项的含义与默认值 | [`guide/CONFIG.md`](guide/CONFIG.md) |
| 用到的 Codex hook：输入字段、输出格式、超时 | [`guide/HOOKS.md`](guide/HOOKS.md) |
| 某条消息为什么没发 / 日志每行什么意思 | [`ops/TROUBLESHOOTING.md`](ops/TROUBLESHOOTING.md) |
| Claude 版历史踩坑（迁移参考） | [`ops/PITFALLS.md`](ops/PITFALLS.md) |
| Claude 版推送通道调研快照 | [`research/PUSH_CHANNELS.md`](research/PUSH_CHANNELS.md) |
| Claude 版历史路线图 | [`plan/ROADMAP.md`](plan/ROADMAP.md) |
| 版本变更 | [`../CHANGELOG.md`](../CHANGELOG.md) |

约定：

- `guide/` 是常青规范，改代码时同步改。
- `research/` 是调研快照，文首标日期；结论被推翻时在文首加更新块，不删原文。
- `ops/PITFALLS.md` 按日期追加，每条含"已回写代码：是/否"。
- `status/` 只回答"现在在哪"和"接下来做什么"，数字不在这里手抄，指向能生成它的命令（`status` 子命令、测试）。
