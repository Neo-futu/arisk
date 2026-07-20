"""當前用戶的 API Key 管理。

明文 Key 只在建立時返回一次；資料庫僅保存 SHA-256 雜湊。這些 Key 用於
Backend 的 X-API-Key 認證，不會把服務間 PROCESSING_API_KEY 暴露到瀏覽器。
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.models import (
    UserApiKey,
    UserApiKeyCreate,
    UserApiKeyCreated,
    UserApiKeyPublic,
)

router = APIRouter()


def _public(record: UserApiKey) -> UserApiKeyPublic:
    return UserApiKeyPublic(
        id=record.id,
        name=record.name,
        masked_key=f"{record.key_prefix}••••{record.last_four}",
        is_active=record.is_active,
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
    )


@router.get("/", response_model=list[UserApiKeyPublic])
def list_api_keys(session: SessionDep, current_user: CurrentUser) -> Any:
    records = session.exec(
        select(UserApiKey)
        .where(UserApiKey.user_id == current_user.id)
        .order_by(UserApiKey.created_at.desc())
    ).all()
    return [_public(record) for record in records]


@router.get("/local-config")
def get_local_api_config(current_user: CurrentUser) -> dict[str, Any]:
    """返回本地客戶端配置說明；內部服務 Key 僅顯示來源，不返回值。"""
    del current_user
    return {
        "name": "本地 ARISK API",
        "api_base_url": settings.BACKEND_PUBLIC_URL.rstrip("/") + settings.API_V1_STR,
        "header_name": "X-API-Key",
        "key_prefix": "arisk_",
        "processing_api": {
            "url": settings.PROCESSING_API_URL,
            "header_name": "X-API-Key",
            "secret_source": "PROCESSING_API_KEY（伺服器 .env，僅服務間使用）",
            "browser_exposed": False,
        },
        "note": "本頁生成的用戶 Key 用於 Backend API；Processing 內部 Key 不會下發到瀏覽器。",
    }


@router.post(
    "/",
    response_model=UserApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    body: UserApiKeyCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    active_count = len(
        session.exec(
            select(UserApiKey).where(
                UserApiKey.user_id == current_user.id,
                UserApiKey.is_active.is_(True),
            )
        ).all()
    )
    if active_count >= 20:
        raise HTTPException(status_code=409, detail="每個用戶最多可有 20 個有效 API Key")

    raw_key = f"arisk_{secrets.token_urlsafe(32)}"
    now = datetime.now(UTC)
    record = UserApiKey(
        user_id=current_user.id,
        name=body.name.strip(),
        key_prefix=raw_key[:12],
        key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        last_four=raw_key[-4:],
        created_at=now,
        expires_at=now + timedelta(days=body.expires_days) if body.expires_days else None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    public = _public(record)
    return UserApiKeyCreated(**public.model_dump(), key=raw_key)


@router.delete("/{key_id}", response_model=UserApiKeyPublic)
def revoke_api_key(
    key_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    record = session.get(UserApiKey, key_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    record.is_active = False
    session.add(record)
    session.commit()
    session.refresh(record)
    return _public(record)
