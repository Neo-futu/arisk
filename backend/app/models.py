from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

IAM_SCHEMA  = "iam"     # 用戶身份認證 + 用戶個人配置
CHAT_SCHEMA = "chatdb"  # AI 對話數據 + 知識庫（獨立於業務數據）


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    __table_args__ = {"schema": IAM_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    __table_args__ = {"schema": IAM_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.user.id", nullable=False, ondelete="CASCADE"
    )


class Role(SQLModel, table=True):
    __tablename__ = "role"
    __table_args__ = {"schema": IAM_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100, unique=True)
    code: str = Field(max_length=100, unique=True)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class Permission(SQLModel, table=True):
    __tablename__ = "permission"
    __table_args__ = {"schema": IAM_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100, unique=True)
    code: str = Field(max_length=150, unique=True)
    description: str | None = Field(default=None, max_length=255)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class Menu(SQLModel, table=True):
    __tablename__ = "menu"
    __table_args__ = {"schema": IAM_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100)
    code: str = Field(max_length=100, unique=True)
    path: str | None = Field(default=None, max_length=255)
    parent_id: uuid.UUID | None = Field(
        default=None, foreign_key=f"{IAM_SCHEMA}.menu.id", ondelete="SET NULL"
    )
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class UserRole(SQLModel, table=True):
    __tablename__ = "user_role"
    __table_args__ = {"schema": IAM_SCHEMA}

    user_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.user.id", primary_key=True, ondelete="CASCADE"
    )
    role_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.role.id", primary_key=True, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permission"
    __table_args__ = {"schema": IAM_SCHEMA}

    role_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.role.id", primary_key=True, ondelete="CASCADE"
    )
    permission_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.permission.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class RoleMenu(SQLModel, table=True):
    __tablename__ = "role_menu"
    __table_args__ = {"schema": IAM_SCHEMA}

    role_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.role.id", primary_key=True, ondelete="CASCADE"
    )
    menu_id: uuid.UUID = Field(
        foreign_key=f"{IAM_SCHEMA}.menu.id", primary_key=True, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ── User API Key ────────────────────────────────────────────────

class UserApiKey(SQLModel, table=True):
    """供腳本/本地客戶端以 X-API-Key 訪問 Backend API 的用戶密鑰。"""
    __tablename__ = "user_api_key"
    __table_args__ = {"schema": IAM_SCHEMA}

    id:           uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id:      uuid.UUID = Field(foreign_key=f"{IAM_SCHEMA}.user.id", index=True, ondelete="CASCADE")
    name:         str       = Field(max_length=100)
    key_prefix:   str       = Field(max_length=16)
    key_hash:     str       = Field(max_length=64, unique=True, index=True)
    last_four:    str       = Field(max_length=4)
    is_active:    bool      = Field(default=True)
    created_at:   datetime  = Field(default_factory=get_datetime_utc)
    expires_at:   datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    last_used_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore


class UserApiKeyCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


class UserApiKeyPublic(SQLModel):
    id:           uuid.UUID
    name:         str
    masked_key:   str
    is_active:    bool
    created_at:   datetime
    expires_at:   datetime | None
    last_used_at: datetime | None


class UserApiKeyCreated(UserApiKeyPublic):
    key: str


# ── Chat Session & Message ─────────────────────────────────────────

class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"
    __table_args__ = {"schema": CHAT_SCHEMA}

    id:         uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id:    uuid.UUID = Field(foreign_key=f"{IAM_SCHEMA}.user.id")
    title:      str       = Field(default="新對話", max_length=100)
    agent_id:   str       = Field(default="general", max_length=50)
    model_id:   str       = Field(default="claude-sonnet-4-6", max_length=100)
    created_at: datetime  = Field(default_factory=get_datetime_utc)
    updated_at: datetime  = Field(default_factory=get_datetime_utc)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    __table_args__ = {"schema": CHAT_SCHEMA}

    id:         uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key=f"{CHAT_SCHEMA}.chat_session.id")
    role:       str       = Field(max_length=20)
    content:    str       = Field(default="")
    tool_calls: str       = Field(default="[]")   # JSON string
    created_at: datetime  = Field(default_factory=get_datetime_utc)


# ── Pydantic schemas (non-table) ──────────────────────────────────

class ChatSessionCreate(SQLModel):
    title:    str = "新對話"
    agent_id: str = "general"
    model_id: str = "claude-sonnet-4-6"


class ChatSessionUpdate(SQLModel):
    title:    str | None = None
    agent_id: str | None = None
    model_id: str | None = None


class ChatSessionPublic(SQLModel):
    id:         uuid.UUID
    title:      str
    agent_id:   str
    model_id:   str
    created_at: datetime
    updated_at: datetime


class ChatMessagePublic(SQLModel):
    id:         uuid.UUID
    session_id: uuid.UUID
    role:       str
    content:    str
    tool_calls: str
    created_at: datetime


class ChatMessageBatch(SQLModel):
    messages: list[dict]   # [{role, content, tool_calls?}]


# ── User Agent Config ──────────────────────────────────────────────

class UserAgentConfig(SQLModel, table=True):
    """每個用戶的專屬 AI Agent 配置（1:1 with User）。"""
    __tablename__ = "user_agent_config"
    __table_args__ = {"schema": IAM_SCHEMA}

    user_id:             uuid.UUID = Field(foreign_key=f"{IAM_SCHEMA}.user.id", primary_key=True)
    agent_name:          str | None = Field(default=None, max_length=100)      # 用戶為 Agent 起的名字
    default_agent_id:    str        = Field(default="general", max_length=50)
    default_model_id:    str        = Field(default="claude-sonnet-4-6", max_length=100)
    custom_instructions: str | None = Field(default=None)                      # 注入 system prompt
    tools_enabled:       str        = Field(default="[]")                      # JSON array
    memory_enabled:      bool       = Field(default=True)
    rag_enabled:         bool       = Field(default=True)
    max_context_turns:   int        = Field(default=40)
    created_at:          datetime   = Field(default_factory=get_datetime_utc)
    updated_at:          datetime   = Field(default_factory=get_datetime_utc)


class UserAgentConfigPublic(SQLModel):
    user_id:             uuid.UUID
    agent_name:          str | None
    default_agent_id:    str
    default_model_id:    str
    custom_instructions: str | None
    tools_enabled:       str
    memory_enabled:      bool
    rag_enabled:         bool
    max_context_turns:   int
    created_at:          datetime
    updated_at:          datetime


class UserAgentConfigUpdate(SQLModel):
    agent_name:          str | None = None
    default_agent_id:    str | None = None
    default_model_id:    str | None = None
    custom_instructions: str | None = None
    tools_enabled:       str | None = None
    memory_enabled:      bool | None = None
    rag_enabled:         bool | None = None
    max_context_turns:   int | None = None


# ── User Custom Tool（用戶個人工具擴展）────────────────────────────

class UserCustomTool(SQLModel, table=True):
    """用戶為自己的 Chat Agent 定義的個人工具。"""
    __tablename__ = "user_custom_tool"
    __table_args__ = {"schema": IAM_SCHEMA}

    id:           uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id:      uuid.UUID = Field(foreign_key=f"{IAM_SCHEMA}.user.id")
    tool_name:    str       = Field(max_length=100)    # snake_case ID
    display_name: str       = Field(max_length=200)
    description:  str       = Field()                  # LLM 工具調用說明
    endpoint:     str       = Field(max_length=500)    # HTTP endpoint
    method:       str       = Field(default="GET", max_length=10)
    parameters:   str       = Field(default="{}")      # JSON Schema string
    enabled:      bool      = Field(default=True)
    created_at:   datetime  = Field(default_factory=get_datetime_utc)
    updated_at:   datetime  = Field(default_factory=get_datetime_utc)


class UserCustomToolPublic(SQLModel):
    id:           uuid.UUID
    tool_name:    str
    display_name: str
    description:  str
    endpoint:     str
    method:       str
    parameters:   str
    enabled:      bool
    created_at:   datetime
    updated_at:   datetime


class UserCustomToolCreate(SQLModel):
    tool_name:    str
    display_name: str
    description:  str
    endpoint:     str
    method:       str = "GET"
    parameters:   str = "{}"
    enabled:      bool = True


class UserCustomToolUpdate(SQLModel):
    display_name: str  | None = None
    description:  str  | None = None
    endpoint:     str  | None = None
    method:       str  | None = None
    parameters:   str  | None = None
    enabled:      bool | None = None
