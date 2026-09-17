import uuid
from datetime import datetime, timezone
from typing import Optional, Literal

from pydantic import EmailStr
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    # 【新增】age 字段 - 用户年龄，可为空（允许不填），最大3位数字
    age: Optional[str] = Field(default=None, max_length=3)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    # ⚠️ items 关系已随 D1.4 删除（模板残留的示例待办表）。
    #    原为：Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
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

# ── Agent 平台相关模型 ──────────────────────────────────────


class ConversationCreate(SQLModel):
    """创建对话请求"""
    title: str = "新对话"


class ChatRequest(SQLModel):
    """发送消息请求"""
    message: str


class ConversationResponse(SQLModel):
    """对话响应"""
    id: uuid.UUID
    title: str
    session_id: str
    created_at: datetime | None = None


class ChatResponse(SQLModel):
    """聊天响应"""
    reply: str
    conversation_id: uuid.UUID


#-- MCP Server相关模型
class MCPServerCreate(SQLModel):
    """创建MCP Server请求
    当用户想要添加一个新的MCP Server时, 发送这个请求。
    """
    name: str = Field(min_length=1, max_length=100)
    transport_type: Literal["sse", "stdio", "streamable_http"]
    url: str | None = Field(default=None, max_length=1000)
    command: str | None = Field(default=None, max_length=500)
    args: list[str] = Field(default_factory=list)
    env_vars: dict = Field(default_factory=dict)
    is_active: bool = True


class MCPServerUpdate(SQLModel):
    """更新MCP Server 请求
    所有字段都是可选的，只更新用户提供的字段
    """
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None,max_length=1000)
    command: str | None = Field(default=None, max_length=500)
    args: list[str] | None = None
    env_vars: dict | None = None
    is_active: bool | None = None

class MCPServerResponse(SQLModel):
    """MCP Server 响应
    返回给用户的 MCP Server信息
    """
    id: uuid.UUID
    name: str
    transport_type: str
    url:str | None
    command: str | None
    args: list[str]
    env_vars: dict
    is_active: bool
    tools: list[dict]
    created_at: datetime | None = None

class MCPServerConnectResponse(SQLModel):
    """MCP Server 连接测试响应
    当用户测试连接MCP Server时返回的结果
    """
    success: bool
    message: str 
    tools: list[dict] = Field(default_factory=list)
    
