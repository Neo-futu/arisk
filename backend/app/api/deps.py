import hashlib
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import TokenPayload, User, UserApiKey
from app.services.portfolio_access import ensure_global_permission, ensure_portfolio_access

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token",
    auto_error=False,
)
user_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str | None, Depends(reusable_oauth2)]
UserApiKeyDep = Annotated[str | None, Depends(user_api_key_header)]


def get_current_user(
    session: SessionDep,
    token: TokenDep,
    api_key: UserApiKeyDep,
) -> User:
    if token:
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
    elif api_key:
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        key_record = session.exec(
            select(UserApiKey).where(
                UserApiKey.key_hash == key_hash,
                UserApiKey.is_active.is_(True),
            )
        ).first()
        now = datetime.now(UTC)
        if not key_record or (key_record.expires_at and key_record.expires_at <= now):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
            )
        user = session.get(User, key_record.user_id)
        key_record.last_used_at = now
        session.add(key_record)
        session.commit()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_portfolio_view(
    fund_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_portfolio_access(session, current_user, fund_id, "VIEW")
    return current_user


def require_portfolio_manage(
    fund_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_portfolio_access(
        session,
        current_user,
        fund_id,
        "MANAGE",
        permission_code="portfolio.manage",
    )
    return current_user


def require_portfolio_trade_manage(
    fund_id: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_portfolio_access(
        session,
        current_user,
        fund_id,
        "MANAGE",
        permission_code="trade.manage",
    )
    return current_user


PortfolioViewer = Annotated[User, Depends(require_portfolio_view)]
PortfolioManager = Annotated[User, Depends(require_portfolio_manage)]
PortfolioTradeManager = Annotated[User, Depends(require_portfolio_trade_manage)]


def get_current_access_admin(
    session: SessionDep,
    current_user: CurrentUser,
) -> User:
    ensure_global_permission(session, current_user, "iam.access.manage")
    return current_user


AccessAdmin = Annotated[User, Depends(get_current_access_admin)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


# ── FSI Processing API Client ──────────────────────────────────────
async def get_processing_client() -> AsyncGenerator[httpx.AsyncClient]:
    """httpx 異步客戶端，帶 Processing API 認證 header，供 FSI 代理路由使用。"""
    headers = {"X-API-Key": settings.PROCESSING_API_KEY}
    async with httpx.AsyncClient(
        base_url=settings.PROCESSING_API_URL,
        headers=headers,
        timeout=30.0,
    ) as client:
        yield client


ProcessingClient = Annotated[httpx.AsyncClient, Depends(get_processing_client)]


async def get_entry_client() -> AsyncGenerator[httpx.AsyncClient]:
    """httpx 異步客戶端，對接 6_entry 內部入口服務。"""
    async with httpx.AsyncClient(
        base_url=settings.ENTRY_API_URL,
        timeout=60.0,
    ) as client:
        yield client


EntryClient = Annotated[httpx.AsyncClient, Depends(get_entry_client)]
