# 求职系统 Web 外壳 V1

这个目录是 Web 版的开发与运维入口。它没有重写原有求职模板，而是在模板外面增加一层适合 2–4 位受邀用户使用的中文 Web 工作台。

每位普通用户对应一个锁定密码、禁止登录的 Linux 系统用户，拥有独立的 `HOME`、Claude 会话与 Git 工作区。浏览器只与 FastAPI 通信；FastAPI 没有 root、sudo、Docker 或读取用户目录的权限。需要越权完成的固定动作由独立的 root Runner 通过 Unix socket 执行。

## 文档导航

- [系统架构](architecture.md)：组件、数据流、信任边界与目录布局。
- [开发环境](development.md)：本地启动、测试和模拟 Runner。
- [API 与 SSE 协议](api.md)：接口、事件信封和错误约定。
- [安全模型](security.md)：身份认证、Linux 隔离、Runner 与威胁模型。
- [Ubuntu / Debian 部署](deployment.md)：systemd、Caddy、Claude Code 和 DeepSeek 配置。
- [管理员与用户手册](guide.md)：开通账号、聊天、文件、额度和停用。
- [模板升级](template-upgrade.md)：版本、哈希、冲突与保护目录。
- [备份与恢复](backup-restore.md)：restic、保留策略和恢复演练。
- [故障排查](troubleshooting.md)：常见错误和诊断顺序。

## V1 范围

已包含账号管理、首次改密、流式聊天、多会话、断线补发、停止任务、上传和 PDF/DOCX 文本提取、文件预览下载、软额度、审计、显式模板升级、Caddy/systemd 和 restic 配置。

V1 不包含公开注册、邮件找回、完整申请看板、在线文件编辑器、MCP 自动审批或高并发调度。意外权限请求会以可读错误结束，系统不会自动放权。

## 生产完成门槛

只有以下项目全部通过，才能把环境标记为“生产可用”：

1. 固定并验证 Claude Code 版本，真实跑通 `/onboard`、续聊、`/match`、`/tailor`、`/pdf` 和 `/scout`。
2. Caddy 正常签发 HTTPS 证书，FastAPI 只监听 `127.0.0.1`，公网无法访问 `/internal/`。
3. 两位测试用户的目录、下载和会话越权测试全部失败。
4. 已配置远程 restic 仓库，完成至少一次 `backup`、`check`、单用户恢复与整站恢复演练。

未配置远程 restic 仓库时，不能声称生产部署完成。
全部演练完成后，以 `deploy/scripts/check-production.sh` 作为可重复执行的最终门槛检查。
