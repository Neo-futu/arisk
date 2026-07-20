"""獨立通知接口：郵件、飛書及企業微信。

其他業務頁只需調用對應 POST 端點，無需了解渠道憑證；Webhook 和 SMTP 憑證
均由伺服器環境變量管理，不接受瀏覽器傳入任意 URL。
"""
from __future__ import annotations

from html import escape
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser
from app.core.config import settings
from app.utils import send_email

router = APIRouter()


class NotificationBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10_000)


class EmailNotificationBody(NotificationBody):
    recipient: EmailStr


class NotificationResult(BaseModel):
    channel: Literal["email", "feishu", "wecom"]
    status: Literal["sent"] = "sent"
    message: str


@router.get("/channels")
def get_notification_channels(current_user: CurrentUser) -> dict[str, Any]:
    del current_user
    return {
        "email": {
            "configured": settings.emails_enabled,
            "description": "SMTP 郵件",
        },
        "feishu": {
            "configured": bool(settings.FEISHU_WEBHOOK_URL),
            "description": "飛書群機器人 Webhook",
        },
        "wecom": {
            "configured": bool(settings.WECOM_WEBHOOK_URL),
            "description": "企業微信群機器人 Webhook",
        },
    }


@router.post("/email", response_model=NotificationResult)
async def notify_by_email(
    body: EmailNotificationBody,
    current_user: CurrentUser,
) -> NotificationResult:
    del current_user
    if not settings.emails_enabled:
        raise HTTPException(status_code=503, detail="郵件渠道尚未配置")
    safe_title = escape(body.title)
    safe_content = escape(body.content).replace("\n", "<br>")
    try:
        await run_in_threadpool(
            send_email,
            email_to=str(body.recipient),
            subject=body.title,
            html_content=f"<h2>{safe_title}</h2><p>{safe_content}</p>",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"郵件發送失敗：{exc}")
    return NotificationResult(channel="email", message=f"郵件已發送至 {body.recipient}")


@router.post("/feishu", response_model=NotificationResult)
async def notify_by_feishu(
    body: NotificationBody,
    current_user: CurrentUser,
) -> NotificationResult:
    del current_user
    if not settings.FEISHU_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="飛書 Webhook 尚未配置")
    data = await _post_webhook(
        settings.FEISHU_WEBHOOK_URL,
        {
            "msg_type": "text",
            "content": {"text": f"【{body.title}】\n{body.content}"},
        },
        "飛書",
    )
    code = data.get("code", data.get("StatusCode", 0))
    if code not in (0, "0", None):
        raise HTTPException(status_code=502, detail=f"飛書發送失敗：{data}")
    return NotificationResult(channel="feishu", message="飛書通知已發送")


@router.post("/wecom", response_model=NotificationResult)
async def notify_by_wecom(
    body: NotificationBody,
    current_user: CurrentUser,
) -> NotificationResult:
    del current_user
    if not settings.WECOM_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="企業微信 Webhook 尚未配置")
    data = await _post_webhook(
        settings.WECOM_WEBHOOK_URL,
        {
            "msgtype": "text",
            "text": {"content": f"【{body.title}】\n{body.content}"},
        },
        "企業微信",
    )
    if data.get("errcode", 0) not in (0, "0", None):
        raise HTTPException(status_code=502, detail=f"企業微信發送失敗：{data}")
    return NotificationResult(channel="wecom", message="企業微信通知已發送")


async def _post_webhook(
    url: str,
    payload: dict[str, Any],
    channel_name: str,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"{channel_name}接口調用失敗：{exc}")
