#!/usr/bin/env bash
# 將舊 arisk 業務庫遷移到 arisk 自有 RDS（上線階段用）。
# 參照 ideclare/scripts/migrate-db.sh；arisk 用自有庫（非共享 Aurora）。
#
# 用法：
#   export SRC_HOST=<舊庫host>
#   export SRC_USER=fsi_user
#   export SRC_DB=fsi_risk
#   export DST_HOST=<arisk-rds-endpoint>   # 上線後 tofu output rds_endpoint
#   export DST_USER=arisk_db_owner         # RDS IAM DB owner（DDL）
#   export DST_DB=fsi_risk
#   bash scripts/migrate-db.sh
#
# 前提：
#   - pg_dump / psql 已安裝（brew install libpq 或 apt install postgresql-client）
#   - 能訪問源庫；能訪問目標 RDS（經 bl-dev / SSM 端口轉發，見 scripts/bl-dev.sh）
#   - 目標庫連接口令：若走 RDS IAM，先 `aws rds generate-db-auth-token` 導出 PGPASSWORD
#
# 注意：arisk 雲端 RDS 的 IaC provision 尚未落地（見 docs/aws-deployment.md），
#       本腳本供上線階段使用。
set -euo pipefail

: "${SRC_HOST:?需設置 SRC_HOST}"
: "${SRC_USER:?需設置 SRC_USER}"
: "${SRC_DB:?需設置 SRC_DB}"
: "${DST_HOST:?需設置 DST_HOST}"
: "${DST_USER:?需設置 DST_USER}"
: "${DST_DB:?需設置 DST_DB}"

DUMP_FILE="/tmp/arisk-$(date +%Y%m%d-%H%M%S).dump"

echo "==> 1. 從源庫 dump（custom 格式，支持並行 restore）"
pg_dump -h "$SRC_HOST" -U "$SRC_USER" -d "$SRC_DB" \
  --format=custom --no-owner --no-acl -f "$DUMP_FILE"
echo "    dump 文件：$DUMP_FILE"

echo "==> 2. 目標 RDS 上確保 database 存在"
psql -h "$DST_HOST" -U "$DST_USER" -d postgres \
  -c "CREATE DATABASE $DST_DB WITH OWNER $DST_USER;" 2>/dev/null || true

echo "==> 3. restore 到目標 RDS"
pg_restore -h "$DST_HOST" -U "$DST_USER" -d "$DST_DB" \
  --no-owner --no-acl --if-exists --clean "$DUMP_FILE"

echo "==> 4. 運行 alembic upgrade head（iam schema）"
( cd "$(dirname "$0")/../backend" && alembic upgrade head )

echo "==> 完成。"
