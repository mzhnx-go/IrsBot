"""CRUD operations for Agent platform models (SQLModel).

Follows the same pattern as existing crud.py and uses
session.exec(select(...)). All functions enforce user_id scoping
for multi-tenant isolation.
"""

import uuid
from collections.abc import Sequence

from sqlmodel import Session, col, func, select

from app.core.db.models import (
    AgentRun,
    Conversation,
    Document,
    KnowledgeBase,
    MCPServer,
    Message,
    Persona,
    ProviderConfig,
    Skill,
)

# ── ProviderConfig CRUD ────────────────────────────────────────


def create_provider_config(
    session: Session, *, user_id: uuid.UUID, **data
) -> ProviderConfig:
    obj = ProviderConfig(user_id=user_id, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_provider_config(
    session: Session, *, provider_id: uuid.UUID, user_id: uuid.UUID
) -> ProviderConfig | None:
    stmt = (
        select(ProviderConfig)
        .where(
            ProviderConfig.id == provider_id,
            ProviderConfig.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_provider_configs(
    session: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> Sequence[ProviderConfig]:
    stmt = (
        select(ProviderConfig)
        .where(ProviderConfig.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def update_provider_config(
    session: Session, *, provider_id: uuid.UUID, user_id: uuid.UUID, **data
) -> ProviderConfig | None:
    obj = get_provider_config(session, provider_id=provider_id, user_id=user_id)
    if obj:
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        session.commit()
        session.refresh(obj)
    return obj


def delete_provider_config(
    session: Session, *, provider_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    obj = get_provider_config(session, provider_id=provider_id, user_id=user_id)
    if obj:
        session.delete(obj)
        session.commit()
        return True
    return False


# ── Conversation CRUD ──────────────────────────────────────────


def create_conversation(
    session: Session,
    *,
    title: str,
    user_id: uuid.UUID,
    session_id: str | None = None,
    persona_id: uuid.UUID | None = None,
) -> Conversation:
    import uuid as _uuid
    if session_id is None:
        session_id = str(_uuid.uuid4())
    obj = Conversation(
        title=title, user_id=user_id, session_id=session_id, persona_id=persona_id
    )
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_conversation(
    session: Session, *, conv_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(
            Conversation.id == conv_id,
            Conversation.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_conversations(
    session: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 20
) -> tuple[list[Conversation], int]:
    stmt_count = select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)
    total = session.exec(stmt_count).one()
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(col(Conversation.updated_at).desc())
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all()), total


def delete_conversation(
    session: Session, *, conv_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    obj = get_conversation(session, conv_id=conv_id, user_id=user_id)
    if obj:
        session.delete(obj)
        session.commit()
        return True
    return False


# ── Message CRUD ───────────────────────────────────────────────


def add_message(
    session: Session,
    *,
    conversation_id: uuid.UUID,
    role: str,
    content: dict,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
) -> Message:
    obj = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    )
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_messages(
    session: Session,
    *,
    conversation_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> Sequence[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(col(Message.created_at).asc())
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


# ── KnowledgeBase CRUD ─────────────────────────────────────────


def create_knowledge_base(
    session: Session, *, name: str, user_id: uuid.UUID, **data
) -> KnowledgeBase:
    obj = KnowledgeBase(user_id=user_id, name=name, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_knowledge_base(
    session: Session, *, kb_id: uuid.UUID, user_id: uuid.UUID
) -> KnowledgeBase | None:
    stmt = (
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_knowledge_bases(
    session: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> Sequence[KnowledgeBase]:
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def delete_knowledge_base(
    session: Session, *, kb_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    obj = get_knowledge_base(session, kb_id=kb_id, user_id=user_id)
    if obj:
        session.delete(obj)
        session.commit()
        return True
    return False


# ── Document CRUD ──────────────────────────────────────────────


def create_document(
    session: Session, *, kb_id: uuid.UUID, user_id: uuid.UUID, **data
) -> Document:
    obj = Document(kb_id=kb_id, user_id=user_id, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_document(
    session: Session, *, doc_id: uuid.UUID, user_id: uuid.UUID
) -> Document | None:
    stmt = (
        select(Document)
        .where(
            Document.id == doc_id,
            Document.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_documents(
    session: Session, *, kb_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> Sequence[Document]:
    stmt = (
        select(Document)
        .where(Document.kb_id == kb_id)
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


# ── MCPServer CRUD ─────────────────────────────────────────────


def create_mcp_server(
    session: Session, *, name: str, transport_type: str, user_id: uuid.UUID, **data
) -> MCPServer:
    obj = MCPServer(name=name, transport_type=transport_type, user_id=user_id, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_mcp_server(
    session: Session, *, server_id: uuid.UUID, user_id: uuid.UUID
) -> MCPServer | None:
    stmt = (
        select(MCPServer)
        .where(
            MCPServer.id == server_id,
            MCPServer.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_mcp_servers(
    session: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> Sequence[MCPServer]:
    stmt = (
        select(MCPServer)
        .where(MCPServer.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def delete_mcp_server(
    session: Session, *, server_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    obj = get_mcp_server(session, server_id=server_id, user_id=user_id)
    if obj:
        session.delete(obj)
        session.commit()
        return True
    return False

def update_mcp_server(
    session: Session, *, server_id: uuid.UUID,
    user_id: uuid.UUID, **data
) -> MCPServer | None:
    """更新MCP server配置"""
    obj = get_mcp_server(session, server_id=server_id, user_id=user_id)
    if obj:
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        session.commit()
        session.refresh(obj)
    return obj


# ── Skill CRUD ─────────────────────────────────────────────────


def get_skill(session: Session, *, name: str) -> Skill | None:
    stmt = select(Skill).where(Skill.name == name)
    return session.exec(stmt).one_or_none()


def list_skills(
    session: Session, *, skip: int = 0, limit: int = 100
) -> Sequence[Skill]:
    stmt = select(Skill).offset(skip).limit(limit)
    return list(session.exec(stmt).all())


def create_skill(
    session: Session, *, name: str, description: str, path: str, **data
) -> Skill:
    obj = Skill(name=name, description=description, path=path, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def delete_skill(session: Session, *, name: str) -> bool:
    obj = get_skill(session, name=name)
    if obj:
        session.delete(obj)
        session.commit()
        return True
    return False


# ── Persona CRUD ───────────────────────────────────────────────


def create_persona(
    session: Session, *, name: str, prompt: str, user_id: uuid.UUID, **data
) -> Persona:
    obj = Persona(name=name, prompt=prompt, user_id=user_id, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_persona(
    session: Session, *, persona_id: uuid.UUID, user_id: uuid.UUID
) -> Persona | None:
    stmt = (
        select(Persona)
        .where(
            Persona.id == persona_id,
            Persona.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_personas(
    session: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> Sequence[Persona]:
    stmt = (
        select(Persona)
        .where(Persona.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def delete_persona(
    session: Session, *, persona_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    obj = get_persona(session, persona_id=persona_id, user_id=user_id)
    if obj:
        session.delete(obj)
        session.commit()
        return True
    return False


# ── AgentRun CRUD ──────────────────────────────────────────────


def create_agent_run(
    session: Session, *, user_id: uuid.UUID, status: str, input_text: str, **data
) -> AgentRun:
    obj = AgentRun(user_id=user_id, status=status, input_text=input_text, **data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def get_agent_run(
    session: Session, *, run_id: uuid.UUID, user_id: uuid.UUID
) -> AgentRun | None:
    stmt = (
        select(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.user_id == user_id,
        )
    )
    return session.exec(stmt).one_or_none()


def list_agent_runs(
    session: Session, *, user_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> Sequence[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.user_id == user_id)
        .order_by(col(AgentRun.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def update_agent_run(
    session: Session, *, run_id: uuid.UUID, user_id: uuid.UUID, **data
) -> AgentRun | None:
    obj = get_agent_run(session, run_id=run_id, user_id=user_id)
    if obj:
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        session.commit()
        session.refresh(obj)
    return obj
