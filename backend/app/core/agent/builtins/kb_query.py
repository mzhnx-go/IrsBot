"""知识库检索工具 — RAG 聚合模式（Phase 14.2）

Agent 的「查资料」能力：LLM 自主决定是否检索、用什么词检索、检索几次。
本模块只回答「怎么查」，不回答「何时查」——那是 LLM 的决策。

身份传递：工具入参只有 LLM 给的 args（可被诱导伪造），user_id 绝不能
走这条通道。正确做法是 Agent 每次运行前调用 set_kb_user() 把身份挂到
ContextVar 上，工具在任意深度随时读取——任务级隔离，并发用户互不串。
"""

import contextvars
import uuid

from sqlmodel import Session, select

from app.core.agent.tools import register_tool
from app.core.db.engine import engine
from app.core.db.models import KnowledgeBase
from app.core.knowledge_base.manager import KBManager

# ContextVar：任务级"用户身份口袋"。default=None 表示"还没人塞过身份"
_current_user_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "kb_current_user_id", default=None
)

# top_k 允许范围：太小检索不到内容，太大撑爆 LLM 上下文
_TOP_K_MIN, _TOP_K_MAX = 1, 10


def set_kb_user(user_id: uuid.UUID | None) -> None:
    """Agent 每次运行开始时调用，把当前用户身份挂到本任务的上下文上"""
    _current_user_id.set(user_id)


@register_tool(
    "knowledge_base_query",
    "Search the user's knowledge bases for relevant document chunks. "
    "Use it when the question may be answered by the user's uploaded documents.",
    category="rag",
)
async def knowledge_base_query(
    query: str,
    kb_id: str | None = None,
    top_k: int = 3,
) -> str:
    """Query the knowledge base and return relevant document chunks.

    Args:
        query: The search query.
        kb_id: Optional specific knowledge base ID to query.
        top_k: Number of results per knowledge base (1-10).
    """
    # ① fail closed：身份缺失就拒绝，绝不回落成"查全部"（多租户铁律）
    user_id = _current_user_id.get()
    if user_id is None:
        return "错误：无法确定当前用户身份，知识库查询被拒绝。"

    # ② 防御 LLM 生成的参数：top_k 夹在 [1, 10]
    top_k = max(_TOP_K_MIN, min(int(top_k or 3), _TOP_K_MAX))

    # ③ 用自己的短会话查"当前用户的库"（含 kb_id 精确过滤，双重保险）
    with Session(engine) as session:
        stmt = select(KnowledgeBase).where(KnowledgeBase.user_id == user_id)
        if kb_id:
            try:
                # LLM 传来的 kb_id 是字符串：先转 UUID 完成格式校验
                stmt = stmt.where(KnowledgeBase.id == uuid.UUID(kb_id))
            except ValueError:
                return f"错误：kb_id '{kb_id}' 不是合法的 UUID。"
        kbs = session.exec(stmt).all()

        if not kbs:
            return "没有找到可查询的知识库（可能尚未创建，或没有上传文档）。"

        mgr = KBManager(session=session)
        sections: list[str] = []
        for kb in kbs:
            # 每个库内部走同一套混合检索（向量 + BM25 + RRF）
            docs = mgr.query(kb_id=kb.id, query=query, top_k=top_k)
            if docs:
                sections.append(f"【知识库：{kb.name}】\n{mgr.get_retrieval_context(docs)}")

    if not sections:
        return "知识库中没有检索到与该问题相关的内容。"

    return "\n\n".join(sections)
