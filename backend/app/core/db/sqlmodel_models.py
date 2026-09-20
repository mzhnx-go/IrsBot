import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import EmailStr, field_validator
from sqlalchemy import DateTime, Text
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
    system_prompt: str | None = Field(
        default=None,
        sa_type=Text,
    )


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


class ConversationRename(SQLModel):
    """重命名对话请求"""

    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        """拒绝纯空白标题（min_length 管不住 "   "），并顺手去掉首尾空白"""
        if not v.strip():
            raise ValueError("标题不能为空白")
        return v.strip()


class ChatRequest(SQLModel):
    """发送消息请求"""
    message: str


class ConversationResponse(SQLModel):
    """对话响应"""
    id: uuid.UUID
    title: str
    session_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChatResponse(SQLModel):
    """聊天响应"""
    reply: str
    conversation_id: uuid.UUID


class MessageOut(SQLModel):
    """会话消息响应（配置台消息列表用）"""
    id: uuid.UUID
    role: str
    content: str
    tool_calls: list[dict] | None = None
    created_at: datetime | None = None


class MessageTruncateRequest(SQLModel):
    """截断消息请求：删除指定消息及其后所有消息（inclusive=False 时保留该条）"""
    message_id: uuid.UUID
    inclusive: bool = True


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


#--系统提示词相关模型
class SystemPromptUpdate(SQLModel):
    """更新系统提示词请求（传空串/null 即清空回落默认）"""
    system_prompt: str | None = None

class SystemPromptPublic(SQLModel):
    """系统提示词状态（GET/PATCH 共用响应）"""
    system_prompt: str | None
    is_custom: bool
    effective_prompt: str


#--运行时配置相关模型
class DeploymentSettingsUpdate(SQLModel):
    """更新部署设置请求。

    目前只有**一个**运行时开关——匿名自助注册是否开放。其余与「模式」
    相关的行为（超管建号、/admin 可见性、数据归属隔离）恒定不变，不随
    开关走，因此这里也只有一个字段。
    """
    open_registration: bool


class DeploymentSettingsPublic(SQLModel):
    """部署设置状态（GET/PATCH 共用响应，仅超管可读）。

    Attributes:
        open_registration: 当前生效值（本表有记录则取本表，否则回落 .env）。
        mode: **派生**的展示标签，由 open_registration 换算，不是独立配置项。
              True → "multi_tenant"（登录页开放注册）；False → "single_user"。
        user_count: 系统内账号数，供前端提示「切回单用户后已有账号仍可登录」。
        env_open_registration: `.env` 里的兜底值。便于管理员理解「本表没有
              记录时，系统在用什么」。超管专属端点，不对外泄露。
    """
    open_registration: bool
    mode: Literal["single_user", "multi_tenant"]
    user_count: int
    env_open_registration: bool


class PublicSettings(SQLModel):
    """匿名可读的公开设置（仅用于登录页判断是否渲染「注册」入口）。

    只暴露这一位布尔：它本身可由「试一次 POST /users/signup」的结果推得，
    因此不构成额外泄露；而登录页必须在**鉴权之前**拿到它。
    """
    open_registration: bool
