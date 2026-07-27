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

`/var/lib/jobhunt/users` 使用 `0711 root:root`：隔离用户可以穿过父目录到达自己的 UUID 目录，但不能列出父目录内容；每个 UUID 用户目录、HOME 和 workspace 仍由 Runner 设置为 `0700`。脚本也会创建 `0750 caddy:caddy` 的 `/var/log/caddy`，供非特权 Caddy 服务写访问日志。可检查：

```bash
stat -c '%a %U:%G %n' /var/lib/jobhunt/users /var/log/caddy
```

预期分别为 `711 root:root` 和 `750 caddy:caddy`。如果前者误设为 `0700`，`jh_*` 用户即使拥有自己的 workspace，也会因为不能穿过父目录而无法初始化 Git。

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

Runner 需要调用 `useradd`、`usermod` 更新 `/etc/passwd`、`/etc/shadow`、`/etc/group` 等系统账号文件，因此 unit 使用 `ProtectSystem=true`，保护 `/usr` 和启动目录但不把 `/etc` 设为只读。启动后检查 Runner 看到的 `/etc`：

```bash
RUNNER_PID="$(systemctl show -p MainPID --value jobhunt-runner.service)"
nsenter -t "$RUNNER_PID" -m findmnt -T /etc -o TARGET,SOURCE,FSTYPE,OPTIONS
```

输出必须包含 `rw`；如果是 `ro`，创建 Web 用户会报 `useradd: cannot lock /etc/passwd`，不要通过手工预建 `jh_*` 用户绕过 Runner。

```bash
sudo -u jobhunt-web sh -c 'set -a; . /etc/jobhunt/web.env; set +a; exec /opt/jobhunt/venv/bin/alembic -c /opt/jobhunt/app/alembic.ini upgrade head'
sudo -u jobhunt-web sh -c 'set -a; . /etc/jobhunt/web.env; set +a; exec /opt/jobhunt/venv/bin/jobhunt-admin bootstrap-admin --username admin'
```

环境文件由 shell 加载，因此值不要包含未转义的 shell 语法；密钥推荐使用十六进制或 URL-safe 字符。

## 5. Caddy

将 `deploy/Caddyfile` 合并到 `/etc/caddy/Caddyfile`，并为 Caddy 服务设置公网域名。专用新服务器可以先备份默认文件再安装；已经承载其他站点时必须合并站点块，不能覆盖：

```bash
cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-jobhunt
install -o root -g root -m 0644 deploy/Caddyfile /etc/caddy/Caddyfile
install -o root -g root -m 0644 deploy/caddy.env.example /etc/jobhunt/caddy.env
install -d -o root -g root -m 0755 /etc/systemd/system/caddy.service.d
install -o root -g root -m 0644 deploy/systemd/caddy-jobhunt.conf /etc/systemd/system/caddy.service.d/jobhunt.conf
```

编辑 `/etc/jobhunt/caddy.env`，`JOBHUNT_DOMAIN` 只写域名或 IP，不带 `https://`、端口和末尾斜杠；同时把 `/etc/jobhunt/web.env` 的 `JOBHUNT_PUBLIC_BASE_URL` 设置为对应的完整 `https://` 地址。

Caddy CLI 不会自动获得 systemd `EnvironmentFile` 中的变量，因此验证前必须显式加载。首次配置、修改 `caddy.env` 或服务当前未运行时使用 `restart`：

```bash
set -a
. /etc/jobhunt/caddy.env
set +a

systemctl daemon-reload
caddy validate --config /etc/caddy/Caddyfile
systemctl restart caddy
```

以后只修改 Caddyfile 且没有修改环境变量时，验证后可使用 `systemctl reload caddy`。确认公网 `/internal/deepseek/anthropic/v1/models` 返回 404，而本机 FastAPI 端口没有监听 `0.0.0.0`。

### 暂无公网域名时的 IP 测试

生产部署仍应使用公网域名和浏览器信任的证书。只有公网 IP 时，可以临时测试完整 HTTPS、Secure Cookie 和反向代理链路：

```bash
# /etc/jobhunt/caddy.env
JOBHUNT_DOMAIN=203.0.113.10

# /etc/jobhunt/web.env
JOBHUNT_COOKIE_SECURE=true
JOBHUNT_PUBLIC_BASE_URL=https://203.0.113.10
```

模板的 `default_sni {$JOBHUNT_DOMAIN}` 用于处理访问裸 IP 时不携带 SNI、且公网 IP 经 NAT 映射到服务器私网地址的情况。加载配置并重启 Caddy/Web 后，可绕过公网回环直接测试本机：

```bash
set -a
. /etc/jobhunt/caddy.env
set +a

caddy validate --config /etc/caddy/Caddyfile
systemctl restart caddy jobhunt-web

curl --insecure \
  --resolve "${JOBHUNT_DOMAIN}:443:127.0.0.1" \
  --silent --output /dev/null --write-out '%{http_code}\n' \
  "https://${JOBHUNT_DOMAIN}/login"
```

预期返回 `200`。Caddy 的本地 CA 不能自动安装到非特权服务或远程浏览器的信任库时，日志可能出现 `failed to install root certificate`；只要随后显示本地证书签发成功，临时测试可以继续。浏览器仍会显示证书不受信任，`--insecure` 也只能用于这一步测试，不能写入生产验收脚本。

获得域名后，将 DNS A/AAAA 记录正确指向服务器，分别更新 `JOBHUNT_DOMAIN` 和 `JOBHUNT_PUBLIC_BASE_URL`，再重启 Caddy 和 Web。之后测试必须去掉 `--insecure`；原 IP 登录 Cookie 不会迁移到新域名，用户重新登录即可，聊天和文件数据不受影响。IP 本地证书模式不满足生产 HTTPS 门槛。

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
