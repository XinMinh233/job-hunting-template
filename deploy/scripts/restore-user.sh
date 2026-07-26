#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "用法：$0 <snapshot-id> <内部用户 UUID>" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/restic-options.sh"

snapshot_id="$1"
user_id="$2"
if [[ ! "$user_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]]; then
  echo "用户 UUID 格式无效" >&2
  exit 2
fi

restore_root="$(mktemp -d /var/tmp/jobhunt-restore-user.XXXXXX)"
echo "先将备份恢复到隔离目录：$restore_root"
restic "${RESTIC_BACKEND_OPTIONS[@]}" restore "$snapshot_id" \
  --include "/var/lib/jobhunt/users/$user_id" \
  --include "/var/cache/jobhunt-backup/control-plane" \
  --target "$restore_root"
echo "用户目录和快照数据库已就绪。停止 Web/Runner 后，按文档恢复文件与聊天数据。"
