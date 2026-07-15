from __future__ import annotations

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    if not api_key or not any(
        hmac.compare_digest(api_key, configured_key)
        for configured_key in settings.api_keys
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
