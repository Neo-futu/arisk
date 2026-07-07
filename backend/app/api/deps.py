from collections.abc import AsyncGenerator, Generator
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


# ── FSI Processing API Client ──────────────────────────────────────
async def get_processing_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx 異步客戶端，帶 Processing API 認證 header，供 FSI 代理路由使用。"""
    headers = {"X-API-Key": settings.PROCESSING_API_KEY}
    async with httpx.AsyncClient(
        base_url=settings.PROCESSING_API_URL,
        headers=headers,
        timeout=30.0,
    ) as client:
        yield client


ProcessingClient = Annotated[httpx.AsyncClient, Depends(get_processing_client)]


async def get_entry_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx 異步客戶端，對接 6_entry 內部入口服務。"""
    async with httpx.AsyncClient(
        base_url=settings.ENTRY_API_URL,
        timeout=60.0,
    ) as client:
        yield client


EntryClient = Annotated[httpx.AsyncClient, Depends(get_entry_client)]
