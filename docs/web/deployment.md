# Ubuntu / Debian 部署

以下流程以受支持的 Ubuntu/Debian、systemd、Python 3.11+ 为前提。首次部署先在一次性测试机完成，不要直接在唯一生产机上试。

## 1. 前置软件

安装 Python、Git、Caddy、restic、`sqlite3`、`rsync`、`jq`、无头 Chrome/Chromium 和中英文字体。Ubuntu/Debian 的基础包可从下面开始；Caddy 按其官方 Debian 仓库安装，以便持续获得安全更新：

```bash
apt update
apt install python3 python3-venv git sqlite3 rsync jq restic \
  fonts-noto-cjk fonts-dejavu-core
```

Debian 可安装发行版的 `chromium`；Ubuntu 的 `chromium` APT 包通常转向 Snap，在受限 systemd 用户下可能不稳定，生产更适合安装并固定 Google Chrome 官方 `.deb`。无论选哪一个，都要先以普通无登录测试 UID 验证 `--headless --print-to-pdf`，再运行 `/pdf` 验收。

随后安装服务器已验证可与 DeepSeek 兼容的固定 Claude Code 版本。记录版本（Chrome 命令按实际安装二选一）：

```bash
claude --version
python3 --version
caddy version
restic version
chromium --version || google-chrome --version
```

禁止为 Claude Code 开启自动更新。把验证过的版本写入 Web 和 Runner 的 `JOBHUNT_CLAUDE_VERSION`；Runner 启动时版本不匹配会直接失败。升级必须先在测试用户中跑完整兼容性验收。

## 2. 安装应用

在仓库根目录以 root 执行：

```bash
bash deploy/install-ubuntu.sh
```

脚本创建专用服务用户、目录、虚拟环境和 systemd 文件，按 `requirements.lock` 安装生产依赖，但故意不启动服务。请检查复制到 `/opt/jobhunt/app` 的版本与 `TEMPLATE_VERSION`。

## 3. 配置环境

```bash
install -o root -g jobhunt-web -m 0640 deploy/web.env.example /etc/jobhunt/web.env
install -o root -g root -m 0600 deploy/runner.env.example /etc/jobhunt/runner.env
install -o root -g root -m 0600 deploy/restic.env.example /etc/jobhunt/restic.env
```

编辑三个文件。`JOBHUNT_SECRET_KEY` 可用 `openssl rand -hex 32` 生成，只放在 Web 环境。真实 `DEEPSEEK_API_KEY` 也只能出现在 `web.env`；Runner 不需要两者。

主模型默认为 `deepseek-v4-pro[1m]`，轻量与子 Agent 默认为 `deepseek-v4-flash`。这是部署配置而不是永久事实：DeepSeek 或 Claude Code 兼容映射变化时，应先更新测试环境、运行六条命令验收，再更新生产固定值。
当前 DeepSeek 的 Claude Code 接入建议同时设置 `JOBHUNT_EFFORT_LEVEL=max`；Web 与 Runner 的两档模型及 effort 必须保持相同值，健康检查会拒绝不一致的配置。

升级前以 [DeepSeek Claude Code 接入文档](https://api-docs.deepseek.com/zh-cn/guides/agent_integrations/claude_code) 和 [Anthropic Claude Code CLI 参考](https://docs.anthropic.com/en/docs/claude-code/cli-usage) 为准，并始终用待部署二进制的 `claude --help` 做最终事实来源。

检查配置：

```bash
set -a
. /etc/jobhunt/web.env
set +a
/opt/jobhunt/venv/bin/jobhunt-admin check-config
```

## 4. 初始化数据库和管理员

先启动 Runner，以便管理员也获得独立 Linux 工作空间：

```bash
systemctl enable --now jobhunt-runner.service
```

```bash
sudo -u jobhunt-web sh -c 'set -a; . /etc/jobhunt/web.env; set +a; exec /opt/jobhunt/venv/bin/alembic -c /opt/jobhunt/app/alembic.ini upgrade head'
sudo -u jobhunt-web sh -c 'set -a; . /etc/jobhunt/web.env; set +a; exec /opt/jobhunt/venv/bin/jobhunt-admin bootstrap-admin --username admin'
```

环境文件由 shell 加载，因此值不要包含未转义的 shell 语法；密钥推荐使用十六进制或 URL-safe 字符。

## 5. Caddy

将 `deploy/Caddyfile` 合并到 `/etc/caddy/Caddyfile`，并为 Caddy 服务设置域名：

```bash
install -o root -g root -m 0644 deploy/caddy.env.example /etc/jobhunt/caddy.env
install -d -o root -g root -m 0755 /etc/systemd/system/caddy.service.d
install -o root -g root -m 0644 deploy/systemd/caddy-jobhunt.conf /etc/systemd/system/caddy.service.d/jobhunt.conf
```

编辑 `/etc/jobhunt/caddy.env` 后验证并重载：

```bash
systemctl daemon-reload
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

确认公网 `/internal/deepseek/anthropic/v1/models` 返回 404，而本机 FastAPI 端口没有监听 `0.0.0.0`。

## 6. 启动

```bash
systemctl enable --now jobhunt-web.service
systemctl enable --now jobhunt-backup.timer
```

检查：

```bash
systemctl status jobhunt-runner jobhunt-web jobhunt-backup.timer
curl --fail --silent http://127.0.0.1:8000/healthz
journalctl -u jobhunt-web -u jobhunt-runner --since today
```

健康检查在生产配置不完整、Runner 不通、DeepSeek Key 缺失或磁盘少于 2 GB 时返回 503。

## 7. 验收

1. 管理员创建两个测试用户，分别登录并修改临时密码。
2. 验证 Linux 用户为 `nologin`、密码锁定、没有 sudo/docker 组。
3. 在 A 的提示中请求读取 B 的 workspace，必须失败；修改下载 path 和 chat/job UUID 也必须失败。
4. 验证每用户串行、全局 3 并发、第四个排队、停止杀死整个 unit。
5. 浏览器在任务中断网后重连，历史增量不丢失、不重复最终文本。
6. 真实执行 `/onboard`、续聊、`/match`、`/tailor`、`/pdf`、`/scout`，检查文件、Git、PDF、tracker 和用户隔离。
7. 配置远程 restic，完成备份、check、单用户和整站恢复演练。

可使用专用、已完成首次改密的测试账号自动跑六条真实工作流。先复制并按测试资料调整 `deploy/live-e2e.commands.example.json`，密码只通过环境变量传入：

```bash
export JOBHUNT_LIVE_PASSWORD='测试账号密码'
/opt/jobhunt/venv/bin/python /opt/jobhunt/app/deploy/scripts/run-live-e2e.py \
  --base-url "https://你的域名" \
  --username "验收账号" \
  --commands /opt/jobhunt/app/deploy/live-e2e.commands.example.json
```

脚本逐任务等待 SSE 完成、核对预期产物、下载并验证 PDF 文件头，并在可读取 Runner registry 时确认 Git 工作区干净。它会真实消耗 DeepSeek API，且会写测试用户的数据，因此禁止使用真实用户账号。

两位测试用户开通后，可先运行只读的主机隔离检查：

```bash
/opt/jobhunt/app/deploy/scripts/verify-isolation.sh <用户A内部UUID> <用户B内部UUID>
```

再执行 systemd 单元静态检查：

```bash
systemd-analyze verify /etc/systemd/system/jobhunt-*.service
```

完成恢复演练后运行生产门槛检查：

```bash
/opt/jobhunt/app/deploy/scripts/check-production.sh
```

它要求 Web、Runner、Caddy 和备份 timer 运行正常，公网内部代理路由为 404，并且远程 restic 最近 48 小时内存在 `jobhunt-daily` 快照。未通过时不得标记生产部署完成。
