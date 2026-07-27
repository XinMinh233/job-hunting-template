#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请以 root 执行" >&2
  exit 1
fi
if [[ ! -f pyproject.toml || ! -d webapp ]]; then
  echo "请在项目仓库根目录执行" >&2
  exit 1
fi

install -d -o root -g root -m 0755 /opt/jobhunt/app
rsync -a \
  --delete \
  --exclude=.git \
  --exclude=.venv \
  --exclude=.runtime \
  --exclude=.pytest_cache \
  --exclude='*.egg-info' \
  ./ /opt/jobhunt/app/
chown -R root:root /opt/jobhunt/app
chmod -R go-w /opt/jobhunt/app

getent group jobhunt-web >/dev/null || groupadd --system jobhunt-web
id jobhunt-web >/dev/null 2>&1 || useradd --system --gid jobhunt-web --home-dir /var/lib/jobhunt --shell /usr/sbin/nologin jobhunt-web

python3 -m venv /opt/jobhunt/venv
/opt/jobhunt/venv/bin/pip install --upgrade pip
/opt/jobhunt/venv/bin/pip install -r /opt/jobhunt/app/requirements.lock
/opt/jobhunt/venv/bin/pip install --no-deps --no-build-isolation /opt/jobhunt/app

install -d -o jobhunt-web -g jobhunt-web -m 0700 /var/lib/jobhunt/app
# 只允许隔离用户穿过父目录；各 UUID 用户目录仍由 Runner 设为 0700。
install -d -o root -g root -m 0711 /var/lib/jobhunt/users
install -d -o root -g root -m 0700 /var/lib/jobhunt-runner
install -d -o jobhunt-web -g jobhunt-web -m 0700 /var/lib/jobhunt-staging
install -d -o root -g jobhunt-web -m 0750 /run/jobhunt
install -d -o root -g root -m 0755 /etc/jobhunt
# deploy/Caddyfile 的文件日志由非特权 caddy 用户创建。
install -d -o caddy -g caddy -m 0750 /var/log/caddy

install -o root -g root -m 0644 deploy/systemd/jobhunt-runner.service /etc/systemd/system/
install -o root -g root -m 0644 deploy/systemd/jobhunt-web.service /etc/systemd/system/
install -o root -g root -m 0644 deploy/systemd/jobhunt-backup.service /etc/systemd/system/
install -o root -g root -m 0644 deploy/systemd/jobhunt-backup.timer /etc/systemd/system/
install -o root -g root -m 0755 deploy/scripts/backup.sh /opt/jobhunt/app/deploy/scripts/
install -o root -g root -m 0755 deploy/scripts/restore-user.sh /opt/jobhunt/app/deploy/scripts/
install -o root -g root -m 0755 deploy/scripts/restore_user_db.py /opt/jobhunt/app/deploy/scripts/
install -o root -g root -m 0755 deploy/scripts/restore-site.sh /opt/jobhunt/app/deploy/scripts/
install -o root -g root -m 0755 deploy/scripts/verify-isolation.sh /opt/jobhunt/app/deploy/scripts/
install -o root -g root -m 0755 deploy/scripts/check-production.sh /opt/jobhunt/app/deploy/scripts/
install -o root -g root -m 0755 deploy/scripts/run-live-e2e.py /opt/jobhunt/app/deploy/scripts/

systemctl daemon-reload
echo "安装文件已就绪。接下来配置 /etc/jobhunt/*.env、Caddy 和管理员；脚本不会擅自启动生产服务。"
