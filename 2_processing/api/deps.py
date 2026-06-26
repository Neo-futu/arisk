"""依賴注入：DB session、API key 驗證、Redis client。"""
from __future__ import annotations

import os

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk",
)
PROCESSING_API_KEY = os.environ.get("PROCESSING_API_KEY", "internal_key_change_me")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis() -> aioredis.Redis:  # type: ignore[return]
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def verify_api_key(key: str | None = Security(api_key_header)) -> str:
    if key != PROCESSING_API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return key
