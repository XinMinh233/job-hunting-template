# 备份与恢复

## 备份内容

每日 `jobhunt-backup.timer` 备份：

- SQLite 在线 `.backup` 生成的 `/var/cache/jobhunt-backup/control-plane/jobhunt.sqlite3`；
- 同批复制的 `/var/cache/jobhunt-backup/control-plane/registry.json`；
- `/var/lib/jobhunt/users`：所有 HOME、Claude 会话、workspace 和 Git。

restic 自带加密和去重。脚本保留最近 7 个带 `jobhunt-daily` 标签的快照并执行 `prune`，随后抽样读取 2.5% 数据做 `check`。

备份脚本使用 SQLite 在线 backup API，而不是在写入期间分别复制主文件和 WAL；恢复后仍必须运行 `PRAGMA integrity_check`。用户目录与控制面快照不是跨文件系统事务，恢复演练应核对用户 UUID、registry 和数据库映射。

## 首次初始化和验证

配置 `/etc/jobhunt/restic.env` 后。腾讯云 COS 上海地域应包含
`AWS_DEFAULT_REGION=ap-shanghai` 和 `RESTIC_S3_BUCKET_LOOKUP=dns`；仓库地址使用
`s3:https://cos.ap-shanghai.myqcloud.com/<BucketName-APPID>/jobhunt-restic`：

```bash
set -a
. /etc/jobhunt/restic.env
set +a
restic -o "s3.bucket-lookup=${RESTIC_S3_BUCKET_LOOKUP:-dns}" init
restic -o "s3.bucket-lookup=${RESTIC_S3_BUCKET_LOOKUP:-dns}" snapshots
systemctl start jobhunt-backup.service
journalctl -u jobhunt-backup.service
restic -o "s3.bucket-lookup=${RESTIC_S3_BUCKET_LOOKUP:-dns}" check
```

上面的 `restic init` 只在新建仓库时执行一次；已有仓库不要重复初始化。项目备份、生产检查和恢复脚本会自动读取相同的 bucket lookup 配置。

备份密码与对象存储凭证不得放在仓库。至少保存一份离线的 restic 密码恢复材料；丢失密码等于永久丢失备份。

## 单用户恢复

1. 先停用用户，记录内部 UUID、Linux 用户名、UID/GID。
2. 运行 `deploy/scripts/restore-user.sh <snapshot> <uuid>`，它把该用户目录、快照 SQLite 和 registry 恢复到随机隔离目录，不覆盖生产。
3. 比较快照 registry 和当前 registry，确认映射没有变化。
4. 停止 Web 和 Runner；把当前用户目录改名保留，而不是删除，并复制当前生产 SQLite 作为演练目标。
5. 先在复制品上恢复该用户的聊天、消息、任务历史、用量和文件元数据：

```bash
/opt/jobhunt/venv/bin/python \
  /opt/jobhunt/app/deploy/scripts/restore_user_db.py \
  --snapshot-db <隔离目录>/var/cache/jobhunt-backup/control-plane/jobhunt.sqlite3 \
  --target-db <生产数据库复制品> \
  --user-id <uuid> \
  --confirm-offline
```

工具要求快照与目标 Alembic revision 一致、用户 UUID 已存在；它不恢复 Web Session 或密码，并会先生成带时间戳的目标数据库副本。快照中的排队/运行任务会转为 `interrupted`。

6. 对复制品运行 `PRAGMA integrity_check` 并核对用户会话数、消息和文件元数据。确认后才对已停机的生产数据库执行同一命令。
7. 将隔离目录中的用户目录放到原路径，依据当前 registry 恢复 UID/GID，HOME/workspace 与用户根目录保持 `0700`；不要用快照中的 UID 数字盲目覆盖。
8. 启动 Runner/Web，先以管理员查看健康，再启用用户并测试 Claude 续聊、文件下载和 Git。
9. 确认无误后再按保留策略清理旧目录与数据库副本。

## 整站恢复

1. 在新服务器安装与快照兼容的固定应用、Claude Code 和系统依赖。
2. 停止 Web、Runner 与备份 timer。
3. 运行 `deploy/scripts/restore-site.sh <snapshot>` 恢复到隔离目录。
4. 从 `control-plane/` 取出数据库和 registry，核对它们与 users 来自同一 restic 快照。
5. 按 registry 重建缺少的 `jh_*` 系统用户，确保用户名与 UID/GID 映射正确。
6. 切换数据目录，检查权限；运行 Alembic 到快照版本所需 revision。
7. 对 SQLite 执行 `PRAGMA integrity_check`，再启动服务。
8. 用两个测试用户检查登录、会话恢复、文件和目录隔离。

恢复脚本故意不自动覆盖生产目录。自动覆盖虽然方便，但会把一次参数错误变成不可恢复的数据事故。

## 演练频率

首次上线前必须演练一次；之后至少每季度演练单用户恢复，每半年演练整站恢复。只有 `restic snapshots` 成功不代表备份可恢复。
