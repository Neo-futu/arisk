"""
scripts/fix_db_grants.py — 修复应用连接用户对 iam / fsi schema 的访问权限。

背景：若部分表由 postgres 超级用户创建（DDL 混用了不同角色），而应用以
POSTGRES_USER（默认 fsi_user）连接，则这些表对应用用户「permission denied」，
导致 /api/v1/access-control/me 等接口 500（典型：iam.user_portfolio_access）。

本脚本以 postgres 超级用户连接，把 iam + fsi schema 下所有表/序列的读写权限
授予应用用户，并设默认权限覆盖将来新建对象。幂等，可重复执行。

用法（在 arisk/ 根目录）：
  python scripts/fix_db_grants.py
  python scripts/fix_db_grants.py --pg-superuser postgres --pg-superpass <密码>
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    import psycopg2
    from dotenv import load_dotenv
except ImportError:
    print("请先安装依赖：pip install psycopg2-binary python-dotenv")
    sys.exit(1)

load_dotenv(ROOT / ".env")

DB_HOST = os.getenv("POSTGRES_SERVER", os.getenv("POSTGRES_HOST", "localhost"))
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "fsi_risk")
APP_USER = os.getenv("POSTGRES_USER", "fsi_user")

SCHEMAS = ["iam", "fsi"]


def parse_args():
    p = argparse.ArgumentParser(description="授予应用用户对 iam/fsi schema 的访问权限")
    p.add_argument("--pg-superuser", default="postgres", help="PostgreSQL 超级用户名")
    p.add_argument("--pg-superpass", default="", help="PostgreSQL 超级用户密码")
    p.add_argument("--app-user", default=APP_USER, help=f"目标应用用户（默认 {APP_USER}）")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    superpass = args.pg_superpass or os.getenv("PG_SUPERPASS", "")
    if not superpass:
        superpass = input(f"请输入 PostgreSQL 超级用户 '{args.pg_superuser}' 的密码：")

    app_user = args.app_user
    print("=" * 60)
    print("  ARISK — 修复 iam/fsi schema 授权")
    print(f"  目标：{DB_HOST}:{DB_PORT}/{DB_NAME}  应用用户：{app_user}")
    print("=" * 60)

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=args.pg_superuser, password=superpass,
    )
    conn.autocommit = True
    cur = conn.cursor()

    for schema in SCHEMAS:
        cur.execute(f'GRANT USAGE ON SCHEMA {schema} TO "{app_user}";')
        cur.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO "{app_user}";'
        )
        cur.execute(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO "{app_user}";'
        )
        # 覆盖将来由 postgres 超级用户新建的对象
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES FOR ROLE {args.pg_superuser} IN SCHEMA {schema} '
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{app_user}";'
        )
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES FOR ROLE {args.pg_superuser} IN SCHEMA {schema} '
            f'GRANT USAGE, SELECT ON SEQUENCES TO "{app_user}";'
        )
        print(f"  ✓ {schema}: 已授予 {app_user} 读写权限 + 默认权限")

    cur.close()
    conn.close()
    print("\n✅ 授权完成。刷新前端即可（无需重启 backend）。")


if __name__ == "__main__":
    main()
