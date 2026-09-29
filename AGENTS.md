# codex-tg-notify 开发约定

本项目把 Codex hook 事件发往 Telegram；`PermissionRequest` 可把一次允许或拒绝的决定交回 Codex。只用 Python 标准库。

- 除 `cli` 外不要向 stdout 写内容。`UserPromptSubmit` 的文本输出会进入模型上下文；只有批准决定应输出 JSON。
- hook 异常只记日志并返回 0，不能让 Codex 因通知失败而中断。
- 改 hook 命令路径时同步更新 `install.HOOK_MARKERS`，否则升级会留下重复 hook。
- 改默认值时同步更新 `config.DEFAULT_CONFIG`、`config.example.json`、`docs/guide/CONFIG.md` 和 README。
- `setup`、`test`、`test --approve` 会发真实 Telegram 消息；离线测试使用假 Bot API。
- `install` 必须保留用户现有的其他 Codex hooks，写入前备份，重复执行不重复追加。

验证：`python3 -m unittest discover -s tests -q`；隔离安装可用 `CODEX_HOME` 指向临时目录。真实配置含 bot token，在仓库外的 `~/.config/codex-tg-notify/config.json`。
