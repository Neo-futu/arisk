"""RDS IAM 认证辅助：为云上 PostgreSQL 生成短期 IAM auth token。

本地默认不启用（`POSTGRES_IAM_AUTH=false`）——只用静态密码 + localhost，
不导入 boto3。仅当云上开启 IAM 认证时才懒加载 boto3 生成 token。

RDS IAM token 有效期约 15 分钟，因此每次新建连接都要重新生成
（见 app/core/db.py 的 do_connect 事件与 alembic/env.py）。
"""

from __future__ import annotations


def generate_iam_token(host: str, port: int, user: str, region: str) -> str:
    """生成一次性的 RDS IAM 数据库认证 token（用作连接口令）。

    仅在 `POSTGRES_IAM_AUTH` 开启时调用；boto3 在此处懒加载，
    本地开发无需安装/配置 boto3。
    """
    import boto3  # 懒加载：本地默认路径不依赖 boto3

    client = boto3.client("rds", region_name=region)
    return client.generate_db_auth_token(
        DBHostname=host,
        Port=port,
        DBUsername=user,
        Region=region,
    )
