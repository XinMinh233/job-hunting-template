#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 || $# -ne 2 ]]; then
  echo "用法（root）：$0 <用户A内部UUID> <用户B内部UUID>" >&2
  exit 2
fi

uuid_pattern='^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
if [[ ! "$1" =~ $uuid_pattern || ! "$2" =~ $uuid_pattern || "$1" == "$2" ]]; then
  echo "需要两个不同且有效的内部用户 UUID" >&2
  exit 2
fi

registry=/var/lib/jobhunt-runner/registry.json
user_a="$(jq -r --arg id "$1" '.[$id].linux_username // empty' "$registry")"
user_b="$(jq -r --arg id "$2" '.[$id].linux_username // empty' "$registry")"
workspace_a="$(jq -r --arg id "$1" '.[$id].workspace // empty' "$registry")"
workspace_b="$(jq -r --arg id "$2" '.[$id].workspace // empty' "$registry")"

if [[ -z "$user_a" || -z "$user_b" || -z "$workspace_a" || -z "$workspace_b" ]]; then
  echo "Runner registry 中缺少测试用户" >&2
  exit 1
fi

shell_a="$(getent passwd "$user_a" | cut -d: -f7)"
shell_b="$(getent passwd "$user_b" | cut -d: -f7)"
[[ "$shell_a" == "/usr/sbin/nologin" && "$shell_b" == "/usr/sbin/nologin" ]]

passwd -S "$user_a" | awk '{exit !($2 == "L" || $2 == "LK")}'
passwd -S "$user_b" | awk '{exit !($2 == "L" || $2 == "LK")}'

! id -nG "$user_a" | tr ' ' '\n' | grep -Eq '^(sudo|docker)$'
! id -nG "$user_b" | tr ' ' '\n' | grep -Eq '^(sudo|docker)$'

runuser -u "$user_a" -- test ! -r "$workspace_b"
runuser -u "$user_b" -- test ! -r "$workspace_a"
runuser -u "$user_a" -- test ! -x "$(dirname "$workspace_b")"
runuser -u "$user_b" -- test ! -x "$(dirname "$workspace_a")"

socket_mode="$(stat -c '%a:%U:%G' /run/jobhunt/runner.sock)"
[[ "$socket_mode" == "660:root:jobhunt-web" ]]

echo "通过：Linux 登录、组、目录互读和 Runner socket 隔离符合预期"

