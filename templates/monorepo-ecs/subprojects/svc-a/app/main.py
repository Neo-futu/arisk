import os
import boto3
import asyncpg
from fastapi import FastAPI

app = FastAPI()

APP_NAME = os.getenv("APP_NAME", "svc-a")
ENV = os.getenv("ENV", "dev")


def get_rds_iam_token() -> str:
    """RDS IAM 认证 token，每次连接时调用（token 有效期 15 分钟）。"""
    client = boto3.client("rds", region_name=os.environ["AWS_REGION"])
    return client.generate_db_auth_token(
        DBHostname=os.environ["DB_HOST"],
        Port=int(os.getenv("DB_PORT", "5432")),
        DBUsername=os.getenv("DB_USER", "svc_a_app_rw"),
    )


async def get_db_conn() -> asyncpg.Connection:
    return await asyncpg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "svc_a"),
        user=os.getenv("DB_USER", "svc_a_app_rw"),
        password=get_rds_iam_token(),
        ssl="require",
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"app": APP_NAME, "env": ENV}
