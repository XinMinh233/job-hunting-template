#!/usr/bin/env bash
set -euo pipefail

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY 未配置}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD 未配置}"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/restic-options.sh"

install -d -m 0700 /var/cache/restic
install -d -m 0700 /var/cache/jobhunt-backup/control-plane
export RESTIC_CACHE_DIR=/var/cache/restic

sqlite3 /var/lib/jobhunt/app/jobhunt.sqlite3 \
  ".backup '/var/cache/jobhunt-backup/control-plane/jobhunt.sqlite3'"
install -m 0600 \
  /var/lib/jobhunt-runner/registry.json \
  /var/cache/jobhunt-backup/control-plane/registry.json

restic "${RESTIC_BACKEND_OPTIONS[@]}" backup \
  --tag jobhunt-daily \
  /var/cache/jobhunt-backup/control-plane \
  /var/lib/jobhunt/users

restic "${RESTIC_BACKEND_OPTIONS[@]}" forget \
  --tag jobhunt-daily \
  --keep-last 7 \
  --prune

restic "${RESTIC_BACKEND_OPTIONS[@]}" check --read-data-subset=2.5%
