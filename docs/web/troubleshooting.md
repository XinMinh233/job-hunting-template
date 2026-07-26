# 故障排查

按“浏览器 → Web → Runner → transient unit → 代理 → DeepSeek”的顺序定位，避免一开始就扩大权限。

## 无法登录

- 查看 `journalctl -u jobhunt-web --since -30min`。
- 连续 5 次失败会锁 15 分钟；记录在 `login_attempts`，不要直接删记录绕过。
- 管理员可重置密码；停用账号即使密码正确也会拒绝。
- 本地 HTTP 开发需 `JOBHUNT_COOKIE_SECURE=false`；生产必须为 true。

## Runner 不可用

```bash
systemctl status jobhunt-runner
ls -l /run/jobhunt/runner.sock
journalctl -u jobhunt-runner --since -30min
```

socket 应为 `root:jobhunt-web 0660`，Web 服务用户必须属于 `jobhunt-web` 组。不要把 socket 改成 `0666`。

## 用户创建失败

检查 `useradd`、`git`、模板目录和 registry 权限。若 Linux 用户/目录已创建而数据库事务失败，不要重新点创建；先对照内部 UUID 审计 registry、`/etc/passwd` 和数据库，人工决定回滚孤儿资源或补齐记录。

## 任务一直排队

- 每用户只能有一个 queued/running 任务。
- 全局 worker 默认 3 个；第四个正常排队。
- 查看 `/api/admin/jobs` 和 `systemctl list-units 'jh-*'`。
- 服务重启会把原 running 标记为 interrupted，不会假装成功。

## Claude 立即失败

在相同 Linux 用户和 workspace 下检查固定 Claude 版本，但不要把真实 DeepSeek Key 复制给用户。常见原因：

- Claude Code 版本与 DeepSeek Anthropic 兼容层不匹配；
- 模型映射已变化；
- 非交互模式遇到未允许工具，无法弹出审批；
- HOME/workspace 权限或 systemd `ReadWritePaths` 错误；
- 代理 Token 过期或账号刚被停用。

权限错误应通过新增一个精确、可审计的允许动作解决。禁止临时加入 `--dangerously-skip-permissions`。

若升级 Claude Code，先比较 `claude --help`。V1 固定版本 2.1.197 已没有旧版 `--max-turns` 参数，轮次限制由 Runner 解析 `stream-json` 后执行；不要把旧参数手工加回启动命令。

## SSE 断线

浏览器 EventSource 会自动重连。服务端事件已写 `job_events`，可带最后 `seq` 重新请求。如果任务仍在跑但没有事件，检查 Runner stdout 是否是合法 NDJSON；原始 stderr 只进入服务日志和净化错误，不进入推理界面。

## DeepSeek 代理错误

- 公网访问 `/internal/...` 必须 404。
- Web 环境必须有真实 `DEEPSEEK_API_KEY`；Runner 环境不应有。
- 检查 `DEEPSEEK_ANTHROPIC_BASE_URL` 是否固定为预期 host。
- 401 多为内部签名/过期问题；403 多为用户停用；502 为上游连接失败。
- usage 缺失时不会猜 Token，管理员面板可能低估；应保存上游样本并适配解析器。

## 上传失败

- 单文件 10 MB、个人累计 100 MB。
- DOCX 解压后最多 50 MB，异常压缩比拒绝。
- PDF 最多 200 页，提取文本最多 200 万字符。
- 路径穿越、绝对路径、符号链接和覆盖都应拒绝。
- 图片型 PDF 可能提取为空；V1 不做 OCR。

## 备份失败

```bash
systemctl status jobhunt-backup.service
journalctl -u jobhunt-backup.service
set -a
. /etc/jobhunt/restic.env
set +a
restic -o "s3.bucket-lookup=${RESTIC_S3_BUCKET_LOOKUP:-dns}" snapshots
restic -o "s3.bucket-lookup=${RESTIC_S3_BUCKET_LOOKUP:-dns}" check
```

不要因为备份失败而删除本地数据腾空间。先修复远程凭证、容量或网络，再人工补跑；磁盘少于 2 GB 时健康检查会报警。
