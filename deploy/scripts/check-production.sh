#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请以 root 执行" >&2
  exit 2
fi

set -a
. /etc/jobhunt/web.env
. /etc/jobhunt/restic.env
. /etc/jobhunt/caddy.env
set +a

: "${DEEPSEEK_API_KEY:?DeepSeek Key 未配置}"
: "${RESTIC_REPOSITORY:?restic 仓库未配置}"
: "${RESTIC_PASSWORD:?restic 密码未配置}"
: "${JOBHUNT_DOMAIN:?公网域名未配置}"

case "$RESTIC_REPOSITORY" in
  *example.com*|*请替换*) echo "restic 仍为示例配置" >&2; exit 1 ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/restic-options.sh"

systemctl is-active --quiet jobhunt-runner.service
systemctl is-active --quiet jobhunt-web.service
systemctl is-active --quiet jobhunt-backup.timer
systemctl is-active --quiet caddy.service

/opt/jobhunt/venv/bin/jobhunt-admin check-config
curl --fail --silent http://127.0.0.1:8000/healthz >/dev/null

internal_status="$(
  curl --silent --output /dev/null --write-out '%{http_code}' \
    "https://${JOBHUNT_DOMAIN}/internal/deepseek/anthropic/v1/models"
)"
[[ "$internal_status" == "404" ]]

latest_backup="$(
  restic "${RESTIC_BACKEND_OPTIONS[@]}" snapshots --tag jobhunt-daily --json |
    jq -r 'sort_by(.time) | last | .time // empty'
)"
if [[ -z "$latest_backup" ]]; then
  echo "没有 jobhunt-daily 远程备份快照" >&2
  exit 1
fi

latest_epoch="$(date --date="$latest_backup" +%s)"
now_epoch="$(date +%s)"
if (( now_epoch - latest_epoch > 172800 )); then
  echo "最近备份超过 48 小时：$latest_backup" >&2
  exit 1
fi

echo "生产门槛通过：服务、HTTPS 内部路由、核心配置和远程备份均有效"
