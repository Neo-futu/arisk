#!/bin/sh
# 容器启动时从环境变量生成 config.yaml，保证镜像内无明文配置，本地可直接检查生成结果。
set -e

cat > /app/config.yaml <<EOF
app_name: ${APP_NAME:-svc-a}
env: ${ENV:-dev}
database:
  host: ${DB_HOST}
  port: ${DB_PORT:-5432}
  name: ${DB_NAME:-svc_a}
  user: ${DB_USER:-svc_a_app_rw}
  region: ${AWS_REGION:-ap-east-1}
  rds_resource_id: ${RDS_RESOURCE_ID}
EOF

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
