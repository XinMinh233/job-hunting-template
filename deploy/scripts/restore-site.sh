#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "用法：$0 <snapshot-id>" >&2
  exit 2
fi

restore_root="$(mktemp -d /var/tmp/jobhunt-restore-site.XXXXXX)"
echo "先将整站备份恢复到隔离目录：$restore_root"
restic restore "$1" --target "$restore_root"
echo "恢复文件已就绪。请按 docs/web/backup-restore.md 的停机流程核验后切换。"

