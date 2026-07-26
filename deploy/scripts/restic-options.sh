#!/usr/bin/env bash

# 为所有备份、检查和恢复命令统一生成 restic 后端选项。
# 腾讯云 COS 的新存储桶仅支持 virtual-hosted-style，因此 S3 仓库默认使用 dns。
RESTIC_BACKEND_OPTIONS=()
if [[ "${RESTIC_REPOSITORY:-}" == s3:* ]]; then
  restic_s3_bucket_lookup="${RESTIC_S3_BUCKET_LOOKUP:-dns}"
  case "$restic_s3_bucket_lookup" in
    auto|dns|path) ;;
    *)
      echo "RESTIC_S3_BUCKET_LOOKUP 只能是 auto、dns 或 path" >&2
      exit 2
      ;;
  esac
  RESTIC_BACKEND_OPTIONS=(-o "s3.bucket-lookup=$restic_s3_bucket_lookup")
fi
